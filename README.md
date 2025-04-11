# Raydium Token Filtering and Sniper Bot

## Overview

The **Raydium Token Sniper Bot** is a Telegram bot designed to monitor the **Raydium** platform on the **Solana blockchain** for newly launched tokens. It filters tokens based on **custom criteria** before launch and provides real-time **token metadata** upon launch.

![Main Bot UI](https://github.com/user-attachments/assets/5a5f805a-a4d3-483d-ae96-421fce03c1d9)

![Filtering UI](https://github.com/user-attachments/assets/0732b12a-827c-40df-a51c-c94344919046)

![Sniping Result UI](https://github.com/user-attachments/assets/4cd26eb6-d7cf-4125-88ff-29e5e2234dd7)

## Features

### 1. **Custom Token Filtering (Pre-Launch)**

The bot automatically filters tokens based on the following user-defined criteria:

- **Token Ownership Renouncement** – The owner must renounce ownership (No mint, freeze, or pause capabilities).
    
- **Social Media Presence** – Token must have a minimum number of active social media accounts (Telegram, Twitter, website).
    
- **Liquidity Locked** – A minimum/maximum amount of liquidity must be locked.
    
- **Liquidity Pool (LP) Tokens** – A minimum percentage of tokens must be in the liquidity pool.
    
- **Developer Holdings** – The developer's holdings must fall within a specified percentage range.
    

### 2. **Real-Time Token Launch Monitoring**

Once a token is live on Raydium, the bot verifies if it meets the filtering criteria.

### 3. **Token Metadata Display**

If a token meets all criteria, the bot displays:

- **Token Name & Symbol**
    
- **Price**
    
- **Contract Address (CA)**
    
- **Market Cap**
    
- **Locked Liquidity**
    
- **Developer Holdings (%)**
    
- **LP Tokens (%)**
    
- **Social Media Links**
    

### 4. **User Interface (UI) & Controls**

The bot provides inline buttons for:

- Setting minimum social media accounts
    
- Setting locked liquidity range
    
- Setting LP token minimum percentage
    
- Setting developer holdings percentage range
    
- **"Set Criteria"** and **"Start Sniping"** buttons for user control
    


## Installation & Setup

### Prerequisites

- Python 3.x
    
- `python-telegram-bot` library
    
- Solana SDK
    
- Raydium API access
    

### Steps

1. **Clone the repository:**

    ```
        git clone https://github.com/ilertha/Raydium-token-filtering-sniping-TelegramBot.git
        cd Raydium-token-filtering-sniping-TelegramBot
    ```
    
2. **Install dependencies:**
    
    ```
    pip install -r requirements.txt
    ```
    
3. **Set up API keys:**
    
    - Obtain **Raydium API V3** access.
        
    - Configure your **Telegram Bot API key**.
        
4. **Run the bot:**
    
    ```
    python bot.py
    ```
    

## Technical Stack

- **Blockchain**: Solana
    
- **Trading Platform**: Raydium
    
- **Programming Language**: Python
    
- **Bot Framework**: python-telegram-bot
