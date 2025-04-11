import os
import re
import json
import timeago
import logging
import asyncio
import aiohttp
import websockets
from datetime import datetime, timezone
from solana.rpc.api import Client
from solders.pubkey import Pubkey
from solders.signature import Signature
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from dotenv import load_dotenv

import pandas as pd
from tabulate import tabulate

from database import insert_token, get_tokens_older_than_1_min, delete_token

load_dotenv()

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
SOLANA_WS_URL = os.getenv('SOLANA_WS_URL')
SOLANA_RPC_URL = os.getenv('SOLANA_RPC_URL')
RAYDIUM_PROGRAM_ID = os.getenv('RAYDIUM_PROGRAM_ID')
DEX_API = os.getenv('DEX_API')
TELEGRAM_CHAT_IDS = [int(chat_id.strip()) for chat_id in os.getenv('TELEGRAM_CHAT_IDS', '').split(',')]

filter_criteria = {
  'social_accounts_min': 1,
  'locked_liquidity_min': 1,
  'locked_liquidity_max': 100,
  'lp_tokens_min': 10.0,
  'dev_hold_min': 1.0,
  'dev_hold_max': 5.0,
  'social_accounts_min_modified': False,
  'locked_liquidity_min_modified': False,
  'locked_liquidity_max_modified': False,
  'lp_tokens_min_modified': False,
  'dev_hold_min_modified': False,
  'dev_hold_max_modified': False,
}

solana_client = Client(SOLANA_RPC_URL)
seen_signatures = set()
base_address = [
  'So11111111111111111111111111111111111111112', # SOL
  'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v', # USDC
  'Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB' # USDT
]

app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
dex_api_semaphore = asyncio.Semaphore(1)


async def fetch_json(url, session):
  '''Fetch JSON data from a URL asynchronously.'''
  try:
    async with session.get(url, timeout=10) as response:
      response.raise_for_status()
      return await response.json()
  except Exception as e:
    logging.error(f'Error fetching URL {url}: {e}')
    return {}


async def get_token_info(token_pubkey):
  '''Fetch token information from Raydium and DEX APIs.'''
  async with aiohttp.ClientSession() as session:
    try:
      token_info_raydium = {}
      raydium_url = (
        f'https://api-v3.raydium.io/pools/info/mint?'
        f'mint1={token_pubkey}&mint2=So11111111111111111111111111111111111111112'
        f'&poolType=all&poolSortField=default&sortType=desc&pageSize=10&page=1'
      )

      while not token_info_raydium:
        logging.info(f'Retrying Raydium API for token {token_pubkey}...')
        raydium_data = await fetch_json(raydium_url, session)
        data = raydium_data.get('data', {}).get('data', [])
        if data:
          token_info_raydium = data[0]
        await asyncio.sleep(5)

      token_info1_dex = await fetch_json(f'{DEX_API}{token_pubkey}', session)
      token_info2_dex = await fetch_json(f'{DEX_API}{token_pubkey}/info', session)
      
      print(f'Token info for token_info_raydium: {token_info_raydium}')
      print(f'Token info for token_info1_dex: {token_info1_dex}')
      print(f'Token info for token_info2_dex: {token_info2_dex}')

      token_info = {
        'name': token_info1_dex.get('data', {}).get('attributes', {}).get('name'),
        'symbol': token_info1_dex.get('data', {}).get('attributes', {}).get('symbol'),
        'mint_address': token_info1_dex.get('data', {}).get('attributes', {}).get('address'),
        'decimals': token_info1_dex.get('data', {}).get('attributes', {}).get('decimals'),
        'image_url': token_info1_dex.get('data', {}).get('attributes', {}).get('image_url'),
        'total_supply': token_info1_dex.get('data', {}).get('attributes', {}).get('total_supply'),
        'price_usd': token_info1_dex.get('data', {}).get('attributes', {}).get('price_usd'),
        'fdv_usd': token_info1_dex.get('data', {}).get('attributes', {}).get('fdv_usd'),
        'total_reserve_in_usd': token_info1_dex.get('data', {}).get('attributes', {}).get('total_reserve_in_usd'),
        'market_cap_usd': token_info1_dex.get('data', {}).get('attributes', {}).get('market_cap_usd'),
        'social_links': {
          'websites': token_info2_dex.get('data', {}).get('attributes', {}).get('websites'),
          'discord_url': token_info2_dex.get('data', {}).get('attributes', {}).get('discord_url'),
          'telegram_handle': token_info2_dex.get('data', {}).get('attributes', {}).get('telegram_handle'),
          'twitter_handle': token_info2_dex.get('data', {}).get('attributes', {}).get('twitter_handle')
        },
        'last_updated': token_info2_dex.get('data', {}).get('attributes', {}).get('holders', {}).get('last_updated', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
        'lp_tokens': token_info2_dex.get('data', {}).get('attributes', {}).get('holders', {}).get('distribution_percentage', {}).get('top_10', 0),
        'liquidity': token_info_raydium.get('tvl', 0),
        'lp_locked': token_info_raydium.get('burnPercent', 0),
        'dev_holdings': token_info2_dex.get('data', {}).get('attributes', {}).get('holders', {}).get('distribution_percentage', {}).get('rest', 0),
      }
      logging.info(f'Token info: {token_info}')
      return token_info
    except Exception as e:
      logging.error(f'Error fetching data for token {token_pubkey}: {e}')
      return {}


async def fetch_tokens_periodically():
  while True:
    try:
      tokens_to_fetch = get_tokens_older_than_1_min()
      for token_id, mint_address in tokens_to_fetch:
        logging.info(f'Fetching data for Token: {mint_address}')
        token_info = await get_token_info(mint_address)
        logging.info(f'Token info: {token_info}')
        delete_token(token_id)
        await send_alert(token_info)
      await asyncio.sleep(10)
    except Exception as e:
      logging.error(f'Error in periodic fetch: {e}')
      await asyncio.sleep(5)


async def getTokens(str_signature):
  try:
    signature = Signature.from_string(str_signature)
    transaction = solana_client.get_transaction(signature, encoding='jsonParsed', max_supported_transaction_version=0).value
    instruction_list = transaction.transaction.transaction.message.instructions

    for instructions in instruction_list:
      if instructions.program_id == Pubkey.from_string(RAYDIUM_PROGRAM_ID):
        print('============NEW POOL DETECTED====================')
        Token0 = instructions.accounts[8]
        Token1 = instructions.accounts[9]

        data = {'Token_Index': ['Token0', 'Token1'], 'Account Public Key': [Token0, Token1]}

        df = pd.DataFrame(data)
        table = tabulate(df, headers='keys', tablefmt='fancy_grid')
        print(table)

        quote_address = Token1 if str(Token0) in base_address else Token0
        logging.info(f'Quote address: {quote_address}')

        insert_token(str(quote_address))
  except Exception as e:
    logging.error(f'Error processing transaction for signature {str_signature}: {e}')


async def keep_alive(ws):
  while True:
    try:
      await asyncio.sleep(10)
      await ws.ping()
    except asyncio.CancelledError:
      break
    except Exception as e:
      logging.error(f'Error sending ping: {e}')
      break


async def get_new_tokens():
  while True:
    try:
      async with websockets.connect(SOLANA_WS_URL) as websocket:
        await websocket.send(json.dumps({
          'jsonrpc': '2.0',
          'id': 1,
          'method': 'logsSubscribe',
          'params': [{'mentions': [RAYDIUM_PROGRAM_ID]}, {'commitment': 'finalized'}]
        }))
        first_resp = await websocket.recv()
        response_dict = json.loads(first_resp)
        if 'result' in response_dict:
          logging.info(f'Subscription successful. Subscription ID: {response_dict['result']}')

        keep_alive_task = asyncio.create_task(keep_alive(websocket))

        async for response in websocket:
          # Check if the response is a valid JSON object
          # Monitoring for new tokens and call getTokens function
        keep_alive_task.cancel()
    except websockets.exceptions.ConnectionClosedError as e:
      logging.error(f'Connection closed: {e}. Retrying...')
      await asyncio.sleep(5)
    except Exception as e:
      logging.error(f'Error: {e}. Retrying...')
      await asyncio.sleep(5)


def format_social_links(social_links):
  formatted_links = []

  # Handling Websites
  if social_links.get('websites') and len(social_links['websites']) > 0:
    for website in social_links['websites']:
      formatted_links.append(f'\t🔗✅ Website: {website}')
  else:
    formatted_links.append('\t🔗❌ No website link available')

  # Handling Discord
  if social_links.get('discord_url'):
    formatted_links.append(f'\t🔗✅ Discord: {social_links['discord_url']}')
  else:
    formatted_links.append('\t🔗❌ No Discord link available')

  # Handling Telegram
  if social_links.get('telegram_handle'):
    telegram_url = f'https://t.me/{social_links['telegram_handle']}'
    formatted_links.append(f'\t🔗✅ Telegram: {telegram_url}')
  else:
    formatted_links.append('\t🔗❌ No Telegram link available')

  # Handling Twitter (now called X)
  if social_links.get('twitter_handle'):
    twitter_url = f'https://x.com/{social_links['twitter_handle']}'
    formatted_links.append(f'\t🔗✅ Twitter: {twitter_url}')
  else:
    formatted_links.append('\t🔗❌ No Twitter link available')

  return '\n'.join(formatted_links)


def format_value(value):
  value = float(value)
  if value >= 1_000_000_000_000:
    return f'{value / 1_000_000_000_000:.2f}T'
  elif value >= 1_000_000_000:
    return f'{value / 1_000_000_000:.2f}B'
  elif value >= 1_000_000:
    return f'{value / 1_000_000:.2f}M'
  elif value >= 1_000:
    return f'{value / 1_000:.2f}K'
  else:
    return f'{value:.2f}'


def get_social_count(token_info):
  all_cnt = 0
  available_cnt = 0
  for key, value in token_info['social_links'].items():
    all_cnt += 1
    if isinstance(value, str) and value:
        available_cnt += 1
    elif isinstance(value, list) and value:
        available_cnt += 1
  return (all_cnt, available_cnt)


def is_invalid(social_accounts, lp_locked, lp_tokens, dev_holding):
  if social_accounts > filter_criteria['social_accounts_min']:
    if lp_locked >= filter_criteria['locked_liquidity_min'] and lp_locked <= filter_criteria['locked_liquidity_max']:
      if lp_tokens >= filter_criteria['lp_tokens_min']:
        if dev_holding >= filter_criteria['dev_hold_min'] and dev_holding <= filter_criteria['dev_hold_max']:
          return False
  return True


async def send_alert(token_info):
  print(f'Sending alert for Token: {token_info}')
  global chat_id
  if not chat_id:
    print('⚠️ No chat id found! Cannot send alert.')
    return
  now = datetime.now(timezone.utc)
  last_updated = token_info.get('last_updated', None)
  if last_updated:
    past = datetime.fromisoformat(last_updated)
  else:
    past = now

  market_cap = token_info['market_cap_usd'] or token_info['fdv_usd'] or 0
  total_supply = float(token_info['total_supply']) / (10 ** int(token_info['decimals']))
  lp_tokens = token_info['liquidity'] / float(token_info['price_usd'])
  lp_tokens_pct = lp_tokens / float(token_info['total_supply']) * 100
  [all_cnt, available_cnt] = get_social_count(token_info)
  text = (
    f'✨ New Pair Spotted! ✨\n\n'
    f'📅 Created: {timeago.format(past, now)}\n'
    f'💎 Token Name: {token_info['name']} ({token_info['symbol']})\n'
    f'📝 Contract: {token_info['mint_address']}\n\n'
    f'💹 Price: ${str(token_info['price_usd'])}\n'
    f'💰 Market Cap: ${format_value(market_cap)}\n'
    f'🔄 Total Supply: {format_value(total_supply)} {token_info['symbol']}\n'
    f'⚖ Liquidity: ${format_value(token_info['liquidity'])} ({token_info['lp_locked']}% locked)\n'
    f'🔹 Tokens in LP: {format_value(lp_tokens)} ({format_value(lp_tokens_pct)}%) \n'
    f'📊 Dev Holdings: {token_info['dev_holdings']}%\n\n'
    f'📫 Socials ({available_cnt}/{all_cnt}):\n{format_social_links(token_info['social_links'])}\n'
  )
  
  if is_invalid(available_cnt, token_info['lp_locked'], lp_tokens_pct, float(token_info['dev_holdings'] or 0)):
    return

  for chat_id in TELEGRAM_CHAT_IDS:
    await app.bot.send_message(chat_id, text=text)
    await app.bot.send_message(chat_id, text='🔬 Continuing snipping new token...')


# Command: Start
async def start(update: Update, context):
  keyboard = [
    [InlineKeyboardButton('🛠 Set Filters', callback_data='set_filters')],
    [InlineKeyboardButton('🔎 Start Sniping', callback_data='start_sniping')]
  ]
  reply_markup = InlineKeyboardMarkup(keyboard)
  if update.callback_query:
    await update.callback_query.message.reply_text(
      '🚀 Welcome to the Raydium Token Sniper Bot! 🚀\n'
      'This bot monitors Raydium on Solana for newly launched tokens.', 
      reply_markup=reply_markup
    )
  elif update.message:
    await update.message.reply_text(
      '🚀 Welcome to the Raydium Token Sniper Bot! 🚀\n'
      'This bot monitors Raydium on Solana for newly launched tokens.',
      reply_markup=reply_markup
    )


async def start_sniping(update: Update, context):
  global chat_id
  chat_id = update.callback_query.message.chat.id
  print(f'Chat ID: {chat_id}')
  await update.callback_query.message.reply_text('🟢 Sniping started... Monitoring new tokens.')
  asyncio.create_task(get_new_tokens())
  asyncio.create_task(fetch_tokens_periodically())


async def set_filters(update: Update, context):
  keyboard = [
    [InlineKeyboardButton(f'📱 Social Media Accounts Min {filter_criteria['social_accounts_min']} {'' if filter_criteria['social_accounts_min_modified'] else '?' }', callback_data='set_filter:social_accounts_min')],
    [InlineKeyboardButton(f'💰 Locked Liquidity Min {filter_criteria['locked_liquidity_min']}% {'' if filter_criteria['locked_liquidity_min_modified'] else '?' }', callback_data='set_filter:locked_liquidity_min')],
    [InlineKeyboardButton(f'💰 Locked Liquidity Max {filter_criteria['locked_liquidity_max']}% {'' if filter_criteria['locked_liquidity_max_modified'] else '?' }', callback_data='set_filter:locked_liquidity_max')],
    [InlineKeyboardButton(f'💎 LP Tokens Min {filter_criteria['lp_tokens_min']}% {'' if filter_criteria['lp_tokens_min_modified'] else '?' }', callback_data='set_filter:lp_tokens_min')],
    [InlineKeyboardButton(f'👨‍💻 Dev Holding Min {filter_criteria['dev_hold_min']}% {'' if filter_criteria['dev_hold_min_modified'] else '?' }', callback_data='set_filter:dev_hold_min')],
    [InlineKeyboardButton(f'👨‍💻 Dev Holding Max {filter_criteria['dev_hold_max']}% {'' if filter_criteria['dev_hold_max_modified'] else '?' }', callback_data='set_filter:dev_hold_max')],
    [InlineKeyboardButton('✅ Confirm ', callback_data='confirm_filters')]
  ]
  reply_markup = InlineKeyboardMarkup(keyboard)

  if update.callback_query:
    await update.callback_query.message.reply_text('Select filters to set:', reply_markup=reply_markup)
  elif update.message:
    await update.message.reply_text('Select filters to set:', reply_markup=reply_markup)


async def handle_filter_input(update: Update, context, filter_key: str):
  user_input = update.message.text

  if filter_key == 'social_accounts_min':
    if not user_input.isdigit():
      await update.message.reply_text('⚠️ Please enter a valid integer value for Social Media Accounts Min. Try again.')
      return
    filter_criteria[filter_key] = int(user_input)
  else:
    if not bool(re.match(r'^\d+(\.\d+)?$', user_input)):
      await update.message.reply_text('⚠️ Please enter a valid positive number. Try again.')
      return
    filter_criteria[filter_key] = float(user_input)

  filter_criteria[f'{filter_key}_modified'] = True
  await update.message.reply_text(f'{filter_key.replace('_', ' ').title()} updated to {filter_criteria[filter_key]}{'%' if filter_key not in ['social_accounts_min'] else ''}.')

  await set_filters(update, context)


async def set_filter(update: Update, context, filter_key: str):
  context.user_data['current_filter'] = filter_key

  await update.callback_query.message.reply_text(f'Please enter a value for {filter_key.replace('_', ' ').title()}:')

  user_input_handler = MessageHandler(filters.TEXT & ~filters.COMMAND, lambda update, context: handle_filter_input(update, context, context.user_data['current_filter']))
  context.application.add_handler(user_input_handler)


async def button_handler(update: Update, context):
  query = update.callback_query
  data = query.data

  if data == 'set_filters':
    await set_filters(update, context)
  elif data == 'start_sniping':
    await start_sniping(update, context)
  elif data.startswith('set_filter:'):
    filter_key = data.split(':')[1]
    await set_filter(update, context, filter_key)
  elif data == 'confirm_filters':
    await start(update, context)


def main():
  app.add_handler(CommandHandler('start', start))
  app.add_handler(CallbackQueryHandler(button_handler))
  app.run_polling()


if __name__ == '__main__':
  main()
