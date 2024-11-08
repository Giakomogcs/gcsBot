from services.binance_client import get_consecutive_trades, get_last_trade
from strategies.risk_manager import RiskManager
import pandas as pd
import pandas_ta as ta
import logging
from datetime import datetime, timedelta

# Configuração do logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()

# Configurações de lucro e perda
MIN_PROFIT_PERCENTAGE = 0.02  # 2% de lucro
STOP_LOSS_PERCENTAGE = 0.01  # 1% de perda

# Quantidade mínima de ativos para considerar venda (ajustada para o limite mínimo da Binance)
min_asset_quantity = 0.0001  # Valor mínimo da Binance para negociação de BTC

# Variáveis globais para armazenar o preço de compra/venda mais recente
last_buy_price = None
last_sell_price = None

def calculate_indicators(df, short_ma_period=10, long_ma_period=60, rsi_period=10, volume_threshold=1.2):
    if len(df) < max(short_ma_period, long_ma_period):
        logger.warning("Dados insuficientes para calcular todos os indicadores. Aguardando mais dados...")
        return None, None, None, None

    # Calcula as Médias Móveis e RSI
    df['SMA_10'] = ta.sma(df['close'], length=short_ma_period)
    df['SMA_60'] = ta.sma(df['close'], length=long_ma_period)
    df['RSI'] = ta.rsi(df['close'], length=rsi_period)
    df['EMA_20'] = ta.ema(df['close'], length=20)
    df['EMA_50'] = ta.ema(df['close'], length=50)

    # Volume filtrado para sinais em mercados de menor volume
    df['Volume_Filter'] = df['volume'] > (volume_threshold * df['volume'].rolling(window=10).mean())

    # Verifica se os indicadores estão prontos para uso
    if df[['SMA_10', 'SMA_60', 'RSI', 'Volume_Filter', 'EMA_20', 'EMA_50']].iloc[-1].isna().any():
        logger.warning("Um ou mais indicadores contêm valores NaN. Verifique os dados históricos.")
        return None, None, None, None, None, None

    short_ma = df['SMA_10'].iloc[-1]
    long_ma = df['SMA_60'].iloc[-1]
    rsi = df['RSI'].iloc[-1]
    volume_filter = df['Volume_Filter'].iloc[-1]
    ema_20 = df['EMA_20'].iloc[-1]
    ema_50 = df['EMA_50'].iloc[-1]

    return short_ma, long_ma, rsi, volume_filter, ema_20, ema_50


def format_quantity(quantity):
    """ Formata a quantidade para 8 casas decimais, sem notação científica. """
    return "{:.8f}".format(quantity)


def small_portfolio_strategy(asset, price, portfolio_manager, df, last_buy, last_sell, max_consecutive_sells=3, max_consecutive_buys=3):
    """
    Estratégia focada em acumular ativos e alavancar o saldo para uma carteira pequena.
    """
    global last_buy_price
    risk_manager = RiskManager(portfolio_manager)
    cash_balance = float(portfolio_manager.get_cash_balance())
    asset_quantity = float(portfolio_manager.get_balance(asset.replace('USDT', '')))
    price = float(price)  # Certifica-se de que o preço é float

    # Define limite de tempo para considerar o último preço de venda como válido (ex: 2 horas)
    max_time_diff = timedelta(hours=2)

    # Verifica se 'last_sell' possui o campo 'time' antes de usá-lo
    if last_sell and 'time' in last_sell:
        last_sell_time = datetime.fromtimestamp(int(last_sell['time']) / 1000)
        recent_sell = (datetime.now() - last_sell_time) < max_time_diff
    else:
        recent_sell = False

    # Obter o número de transações consecutivas para compra e venda
    consecutive_sells = get_consecutive_trades(asset, 'sell')
    consecutive_buys = get_consecutive_trades(asset, 'buy')

    # Tentativa de compra
    logger.info("Tentando realizar compra...")
    if consecutive_buys < max_consecutive_buys and (not recent_sell or price < float(last_sell['price']) * (1 - 2 * STOP_LOSS_PERCENTAGE)):
        logger.info(f"Considerando compra (consecutivas de compra: {consecutive_buys})")
        short_ma, long_ma, rsi, volume_filter, _, _ = calculate_indicators(df)
        
        if short_ma < long_ma or rsi < 40:
            # Calcula a quantidade a comprar e formata para 8 casas decimais
            quantity_to_buy = min((cash_balance * portfolio_manager.get_investment_percentage()) / price, portfolio_manager.get_investment_percentage() * asset_quantity)
            quantity_to_buy = format_quantity(max(quantity_to_buy, min_asset_quantity))

            # Confirma se o valor não é zero e está no formato correto
            if float(quantity_to_buy) >= min_asset_quantity and risk_manager.can_trade(asset, 'buy', float(quantity_to_buy), price, df):
                last_buy_price = price
                logger.info("Condições de compra atendidas. Executando compra.")
                return {
                    'asset': asset,
                    'quantity': float(quantity_to_buy),
                    'price': price,
                    'type': 'buy',
                    'reason': "Compra em oportunidade de curto prazo com base em indicadores e limite de compras consecutivas"
                }
            else:
                logger.info("Condições de compra atendidas, mas o RiskManager bloqueou a transação.")
        else:
            logger.info(f"Condições de compra não atendidas: short_ma ({short_ma}) >= long_ma ({long_ma}) ou rsi ({rsi}) >= 40.")
    else:
        logger.info(f"Limite de compras consecutivas atingido ({consecutive_buys} / {max_consecutive_buys}) ou condições de venda recentes ainda válidas.")

    # Tentativa de venda se compra não foi realizada
    logger.info("Tentando realizar venda...")
    if consecutive_sells < max_consecutive_sells and last_buy and price > float(last_buy['price']) * (1 + MIN_PROFIT_PERCENTAGE):
        logger.info(f"Considerando venda (consecutivas de venda: {consecutive_sells})")
        quantity_to_sell = min(asset_quantity * portfolio_manager.get_investment_percentage(), asset_quantity - min_asset_quantity)
        quantity_to_sell = format_quantity(max(quantity_to_sell, min_asset_quantity))

        if float(quantity_to_sell) >= min_asset_quantity and risk_manager.can_trade(asset, 'sell', float(quantity_to_sell), price, df):
            logger.info("Condições de venda atendidas. Executando venda.")
            return {
                'asset': asset,
                'quantity': float(quantity_to_sell),
                'price': price,
                'type': 'sell',
                'reason': "Venda para lucro a curto prazo em carteira pequena com limite de vendas consecutivas"
            }
        else:
            logger.info("Condições de venda atendidas, mas o RiskManager bloqueou a transação.")
    else:
        logger.info(f"Limite de vendas consecutivas atingido ({consecutive_sells} / {max_consecutive_sells}) ou condições de lucro não atendidas.")

    # Mantém a posição quando as transações consecutivas atingem o limite
    if consecutive_sells >= max_consecutive_sells or consecutive_buys >= max_consecutive_buys:
        logger.info(f"Limite de transações consecutivas atingido (Vendas: {consecutive_sells}, Compras: {consecutive_buys}). Mantendo posição.")
        return {
            'asset': asset,
            'quantity': 0,
            'price': price,
            'type': 'hold',
            'reason': "Hold - Limite de transações consecutivas atingido"
        }

    logger.info("Carteira pequena: Nenhuma transação realizada.")
    return {
        'asset': asset,
        'quantity': 0,
        'price': price,
        'type': 'hold',
        'reason': "Hold - Estratégia de acúmulo em carteira pequena"
    }


def mature_portfolio_strategy(asset, price, portfolio_manager, df, indicators, last_buy, last_sell):
    """
    Estratégia focada em tendências e indicadores de mercado para uma carteira madura.
    """
    global last_buy_price, last_sell_price
    risk_manager = RiskManager(portfolio_manager)
    buy_score = 0.0
    sell_score = 0.0

    # Condições de compra com base em indicadores e preço
    if last_buy and price < last_buy['price'] * (1 - STOP_LOSS_PERCENTAGE):
        buy_score += 1.0
    buy_score += indicators['volume_score']
    buy_score += indicators['ma_score']

    # Condições de venda com base em indicadores e preço
    if last_sell and price > last_sell['price'] * (1 + MIN_PROFIT_PERCENTAGE):
        sell_score += 1.0
    sell_score += indicators['sell_rsi_score']
    sell_score += indicators['sell_ma_score']

    buy_threshold = 1.5
    sell_threshold = 1.5
    cash_balance = portfolio_manager.get_cash_balance()
    asset_quantity = portfolio_manager.get_balance(asset.replace('USDT', ''))
    

    quantity_to_buy = format_quantity(min((cash_balance * portfolio_manager.get_investment_percentage()) / price, portfolio_manager.get_investment_percentage() * asset_quantity))
    quantity_to_sell = format_quantity(min(asset_quantity * portfolio_manager.get_investment_percentage(), asset_quantity - min_asset_quantity))

    # Decisão de compra
    if buy_score >= buy_threshold and cash_balance >= price * float(quantity_to_buy):
        logger.info(f"Condições de compra atendidas com pontuação total {buy_score}/{buy_threshold}")
        if risk_manager.can_trade(asset, 'buy', float(quantity_to_buy), price, df):
            last_buy_price = price
            return {
                'asset': asset,
                'quantity': quantity_to_buy,
                'price': price,
                'type': 'buy',
                'reason': f"Compra baseada em indicadores com pontuação {buy_score}"
            }

    # Decisão de venda
    if sell_score >= sell_threshold and asset_quantity >= min_asset_quantity:
        potential_profit = (price - last_buy_price) / last_buy_price if last_buy_price else 0
        if potential_profit >= MIN_PROFIT_PERCENTAGE and risk_manager.can_trade(asset, 'sell', float(quantity_to_sell), price, df):
            last_sell_price = price
            return {
                'asset': asset,
                'quantity': quantity_to_sell,
                'price': price,
                'type': 'sell',
                'reason': f"Venda para lucro com pontuação {sell_score}"
            }

    logger.info(f"Posição mantida (Compra: {buy_score}, Venda: {sell_score}) para carteira madura.")
    return {
        'asset': asset,
        'quantity': 0,
        'price': price,
        'type': 'hold',
        'reason': "Hold - Estratégia de indicadores para carteira madura"
    }


def trading_decision(asset, price, portfolio_manager, df):
    """
    Escolhe a estratégia baseada no tamanho da carteira.
    """
    last_buy, last_sell = get_last_trade(asset)
    short_ma, long_ma, rsi, volume_filter, ema_20, ema_50 = calculate_indicators(df)

    # Avalia se a carteira é pequena
    asset_quantity = portfolio_manager.get_balance(asset.replace('USDT', ''))
    cash_balance = portfolio_manager.get_cash_balance()

    if asset_quantity < 0.06:  # Arbitrário para definir uma carteira pequena
        return small_portfolio_strategy(asset, price, portfolio_manager, df, last_buy, last_sell)
    else:
        indicators = {
            'volume_score': 1 if volume_filter else min(df['volume'].iloc[-1] / (1.4 * df['volume'].rolling(window=10).mean().iloc[-1]), 0.5),
            'ma_score': min(short_ma - long_ma / long_ma, 1) if short_ma > long_ma else 0,
            'sell_rsi_score': min((rsi - 60) / 40, 1) if rsi > 60 else 0,
            'sell_ma_score': min(abs(short_ma - long_ma) / long_ma, 1) if short_ma < long_ma else 0,
        }
        return mature_portfolio_strategy(asset, price, portfolio_manager, df, indicators, last_buy, last_sell)
