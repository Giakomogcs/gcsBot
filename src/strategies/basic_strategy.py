import json
import os
from services.binance_client import get_consecutive_trades, get_recent_prices

from strategies.risk_manager import RiskManager
from services.transaction_manager import clean_transactions_outside_market_average, get_last_transaction_time, load_transactions, save_block_counts, save_transactions, add_transaction, get_average_price, get_last_transaction, load_block_counts
import pandas as pd
import pandas_ta as ta
import logging
from datetime import datetime, timedelta


# Configuração do logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()

# Quantidade mínima de ativos para considerar venda
min_asset_quantity = 0.0001  # Valor mínimo da Binance para negociação de BTC

# Carregar histórico de transações
transactions = load_transactions()
last_buy = get_last_transaction(transactions, 'buys')
last_sell = get_last_transaction(transactions, 'sells')



def calculate_indicators(df, short_ma_period=10, long_ma_period=150, rsi_period=12, volume_threshold=1.1, atr_period=14, adx_period=14):
    if len(df) < max(short_ma_period, long_ma_period, atr_period, adx_period):
        logger.warning("Dados insuficientes para calcular todos os indicadores. Aguardando mais dados...")
        return None, None, None, None, None, None, None, None

    # Calcula os indicadores
    df['SMA_10'] = ta.sma(df['close'], length=short_ma_period)
    df['SMA_60'] = ta.sma(df['close'], length=long_ma_period)
    df['RSI'] = ta.rsi(df['close'], length=rsi_period)
    df['EMA_20'] = ta.ema(df['close'], length=20)
    df['EMA_50'] = ta.ema(df['close'], length=50)
    df['ATR'] = ta.atr(df['high'], df['low'], df['close'], length=atr_period)

    # Calcular ADX e selecionar apenas a coluna "ADX"
    adx_df = ta.adx(df['high'], df['low'], df['close'], length=adx_period)
    if isinstance(adx_df, pd.DataFrame) and 'ADX_14' in adx_df.columns:  # Ajuste para o nome da coluna padrão
        df['ADX'] = adx_df['ADX_14']
    else:
        df['ADX'] = None
        logger.warning("Erro ao calcular o ADX. Dados insuficientes ou formato inesperado.")

    df['Volume_Filter'] = df['volume'] > (volume_threshold * df['volume'].rolling(window=10).mean())

    # Verifica se os indicadores foram calculados corretamente
    missing_indicators = []
    if df[['SMA_10', 'SMA_60', 'RSI', 'Volume_Filter', 'ATR', 'ADX', 'EMA_20', 'EMA_50']].iloc[-1].isna().any():
        missing_indicators = df[['SMA_10', 'SMA_60', 'RSI', 'Volume_Filter', 'ATR', 'ADX', 'EMA_20', 'EMA_50']].iloc[-1].isna()
        logger.warning(f"Indicadores ausentes: {missing_indicators[missing_indicators].index.tolist()}")

    # Valores finais para retorno
    short_ma = df['SMA_10'].iloc[-1] if not pd.isna(df['SMA_10'].iloc[-1]) else None
    long_ma = df['SMA_60'].iloc[-1] if not pd.isna(df['SMA_60'].iloc[-1]) else None
    rsi = df['RSI'].iloc[-1] if not pd.isna(df['RSI'].iloc[-1]) else None
    volume_filter = df['Volume_Filter'].iloc[-1] if not pd.isna(df['Volume_Filter'].iloc[-1]) else None
    atr = df['ATR'].iloc[-1] if not pd.isna(df['ATR'].iloc[-1]) else None
    adx = df['ADX'].iloc[-1] if not pd.isna(df['ADX'].iloc[-1]) else None
    ema_20 = df['EMA_20'].iloc[-1] if not pd.isna(df['EMA_20'].iloc[-1]) else None
    ema_50 = df['EMA_50'].iloc[-1] if not pd.isna(df['EMA_50'].iloc[-1]) else None

    return short_ma, long_ma, rsi, volume_filter, atr, adx, ema_20, ema_50




def format_quantity(quantity):
    """Formata a quantidade para 8 casas decimais, sem notação científica."""
    return "{:.8f}".format(quantity)

def log_transaction_details(transaction_type, asset, quantity, price, profit=None):
    if profit is not None:
        logger.info(f"{transaction_type.capitalize()} realizado para {asset}. Quantidade: {quantity}, Preço: {price}, Lucro: {profit}")
    else:
        logger.info(f"{transaction_type.capitalize()} realizado para {asset}. Quantidade: {quantity}, Preço: {price}")

def calculate_profit(last_price, current_price):
    return (current_price - last_price) / last_price


def small_portfolio_strategy(asset, price, portfolio_manager, df, max_consecutive_trades=5):
    global last_buy, last_sell
    consecutive_sell_blocks, consecutive_buy_blocks = load_block_counts()

    risk_manager = RiskManager(portfolio_manager)
    cash_balance = float(portfolio_manager.get_cash_balance())
    asset_quantity = float(portfolio_manager.get_balance(asset.replace('USDT', '')))
    price = float(price)

    # Calcular indicadores
    short_ma, long_ma, rsi, volume_filter, atr, adx, ema_20, ema_50 = calculate_indicators(df)
    if None in (short_ma, long_ma, rsi, volume_filter, atr, adx):
        logger.warning("Indicadores insuficientes para tomar decisão. Mantendo posição.")
        return {
            'asset': asset,
            'quantity': 0,
            'price': price,
            'type': 'hold',
            'reason': "Hold - Indicadores insuficientes"
        }

    # Ajuste dinâmico de lucros e perdas com base no ATR
    MAX_PROFIT = 0.05  # 5%
    MAX_STOP_LOSS = 0.03  # 3%
    MIN_PROFIT_PERCENTAGE = min(max(0.0015, atr / price), MAX_PROFIT)
    STOP_LOSS_PERCENTAGE = min(max(0.0020, atr / price), MAX_STOP_LOSS)

    # Ajuste adicional para mercados laterais
    if adx < 25:
        MIN_PROFIT_PERCENTAGE = min(MIN_PROFIT_PERCENTAGE, 0.02)
        STOP_LOSS_PERCENTAGE = min(STOP_LOSS_PERCENTAGE, 0.01)

    logger.info(f"ATR: {atr:.6f}, ADX: {adx:.2f}")
    logger.info(f"Lucro mínimo ajustado: {MIN_PROFIT_PERCENTAGE * 100:.2f}%, Stop-Loss ajustado: {STOP_LOSS_PERCENTAGE * 100:.2f}%")

    # Logs detalhados dos indicadores
    logger.info(f"Indicadores: short_ma={short_ma:.2f}, long_ma={long_ma:.2f}, rsi={rsi:.2f}, volume_filter={volume_filter}, ema_20={ema_20:.2f}, ema_50={ema_50:.2f}")

    # ----- Decisão de Compra -----
    def decide_buy():
        if short_ma < long_ma * 0.995 and rsi < 50 and volume_filter:
            quantity_to_buy = (cash_balance * portfolio_manager.get_investment_percentage()) / price
            quantity_to_buy = format_quantity(max(quantity_to_buy, min_asset_quantity))

            if risk_manager.can_trade(asset, 'buy', float(quantity_to_buy), price, df):
                logger.info(f"Condição de compra atendida: short_ma < long_ma, RSI < 50, volume_filter=True. Comprando {quantity_to_buy} {asset}.")
                add_transaction(transactions, "buys", price)
                consecutive_buy_blocks = 0
                save_block_counts(consecutive_sell_blocks, consecutive_buy_blocks)
                return {
                    'asset': asset,
                    'quantity': float(quantity_to_buy),
                    'price': price,
                    'type': 'buy',
                    'reason': "Compra baseada nos indicadores"
                }
            else:
                logger.info("Compra bloqueada pelo RiskManager.")
        else:
            logger.info("Condições de compra não atendidas.")
            logger.info(f"Motivos: short_ma={short_ma}, long_ma={long_ma}, rsi={rsi}, volume_filter={volume_filter}, cash_balance={cash_balance:.2f}")
        return None

    # ----- Decisão de Venda -----
    def decide_sell():
        average_buy_price = get_average_price(transactions, "buys")
        target_sell_price = average_buy_price * (1 + MIN_PROFIT_PERCENTAGE)

        if price >= target_sell_price:
            quantity_to_sell = format_quantity(min(asset_quantity, asset_quantity - min_asset_quantity))

            if risk_manager.can_trade(asset, 'sell', float(quantity_to_sell), price, df):
                profit = calculate_profit(average_buy_price, price)
                logger.info(f"Condição de venda atendida: preço >= target_sell_price. Vendendo {quantity_to_sell} {asset} com lucro de {profit * 100:.2f}%.")
                add_transaction(transactions, "sells", price)
                consecutive_sell_blocks = 0
                save_block_counts(consecutive_sell_blocks, consecutive_buy_blocks)
                return {
                    'asset': asset,
                    'quantity': float(quantity_to_sell),
                    'price': price,
                    'type': 'sell',
                    'reason': "Venda baseada no lucro"
                }
            else:
                logger.info("Venda bloqueada pelo RiskManager.")
        else:
            logger.info("Condições de venda não atendidas.")
            logger.info(f"Motivos: price={price:.2f}, target_sell_price={target_sell_price:.2f}, asset_quantity={asset_quantity:.8f}")
        return None

    # Executa decisões
    buy_decision = decide_buy()
    if buy_decision:
        return buy_decision

    sell_decision = decide_sell()
    if sell_decision:
        return sell_decision

    # Nenhuma decisão tomada
    logger.info("Nenhuma condição de compra ou venda atendida. Mantendo posição.")
    return {
        'asset': asset,
        'quantity': 0,
        'price': price,
        'type': 'hold',
        'reason': "Hold - Nenhuma condição de trade atendida"
    }



def mature_portfolio_strategy(asset, price, portfolio_manager, df, indicators):
    global last_buy, last_sell
    logger.info("Estratégia Mature Portfolio - Sistema de Pontuação Ajustado.")
    
    # Instanciando o Gerenciador de Risco
    risk_manager = RiskManager(portfolio_manager)

    # Condições adicionais baseadas nas médias curtas
    average_buy_price = get_average_price(transactions, "buys")
    average_sell_price = get_average_price(transactions, "sells")
    
    # Configurações de lucro e perda para uma estratégia madura
    MIN_PROFIT_PERCENTAGE = 0.01  # 1% de lucro alvo
    STOP_LOSS_PERCENTAGE = 0.015  # 1.5% de perda tolerada

    # Critérios de pontuação para compra e venda
    buy_score = 0.0
    sell_score = 0.0

    # 1. Preço em Relação ao Last Buy/Last Sell com Peso 60%
    price_buy_score = 0
    price_sell_score = 0
    if last_buy:
        price_buy_score += max(0, min(2.0, (last_buy * (1 - 2 * STOP_LOSS_PERCENTAGE) - price) / (last_buy * STOP_LOSS_PERCENTAGE)))
    if average_buy_price:
        price_buy_score += max(0, min(2.0, (average_buy_price * (1 - 2 * STOP_LOSS_PERCENTAGE) - price) / (average_buy_price * STOP_LOSS_PERCENTAGE)))
    
    if last_sell:
        price_sell_score += max(0, min(2.0, (price - last_sell * (1 + MIN_PROFIT_PERCENTAGE)) / (last_sell * MIN_PROFIT_PERCENTAGE)))
    if average_sell_price:
        price_sell_score += max(0, min(2.0, (price - average_sell_price * (1 + MIN_PROFIT_PERCENTAGE)) / (average_sell_price * MIN_PROFIT_PERCENTAGE)))
    
    buy_score += price_buy_score * 0.6
    sell_score += price_sell_score * 0.6
    logger.info(f"Pontuação do Preço: compra={price_buy_score * 0.6:.2f}, venda={price_sell_score * 0.6:.2f}")

    # 2. Média Móvel com Peso 20%
    ma_score = min(abs(indicators['ma_score']), 1.5)
    if indicators['ma_score'] > 0:
        buy_score += ma_score * 0.2
        logger.info(f"Pontuação da Média Móvel para Compra: {ma_score * 0.2:.2f}")
    else:
        sell_score += ma_score * 0.2
        logger.info(f"Pontuação da Média Móvel para Venda: {ma_score * 0.2:.2f}")

    # 3. Volume com Peso 15%
    volume_score = min(indicators['volume_score'], 1)
    buy_score += volume_score * 0.15
    sell_score += volume_score * 0.15
    logger.info(f"Pontuação de Volume: compra={volume_score * 0.15:.2f}, venda={volume_score * 0.15:.2f}")

    # 4. RSI com Peso 5%
    rsi_score_buy = max(0, 1 - indicators['rsi'] / 50) if indicators['rsi'] < 50 else 0
    rsi_score_sell = max(0, (indicators['rsi'] - 50) / 50) if indicators['rsi'] > 50 else 0
    buy_score += rsi_score_buy * 0.05
    sell_score += rsi_score_sell * 0.05
    logger.info(f"Pontuação de RSI: compra={rsi_score_buy * 0.05:.2f}, venda={rsi_score_sell * 0.05:.2f}")

    # Somatório dos Scores
    logger.info(f"Pontuação final de compra: {buy_score:.2f}, Pontuação final de venda: {sell_score:.2f}")

    # Definir limite de ativação para compra/venda
    buy_threshold = 4  # Meta de pontuação para compra
    sell_threshold = 4 # Meta de pontuação para venda

    # Dados da carteira e cálculo da quantidade de compra/venda
    cash_balance = portfolio_manager.get_cash_balance()
    asset_quantity = portfolio_manager.get_balance(asset.replace('USDT', ''))

    # Quantidade ajustada para uma estratégia madura e poder de compra maior
    quantity_to_buy = format_quantity((cash_balance * portfolio_manager.get_investment_percentage()) / price)
    quantity_to_sell = format_quantity(min(asset_quantity * portfolio_manager.get_investment_percentage(), asset_quantity - min_asset_quantity))

    # Decisão de compra
    if buy_score >= buy_threshold and cash_balance >= price * float(quantity_to_buy) and risk_manager.can_trade(asset, 'buy', float(quantity_to_buy), price, df):
        last_buy = price
        logger.info(f"Compra com pontuação de {buy_score}/{buy_threshold}")
        add_transaction(transactions, "buys", price)
        log_transaction_details("compra", asset, quantity_to_buy, price)
        return {
            'asset': asset,
            'quantity': quantity_to_buy,
            'price': price,
            'type': 'buy',
            'reason': f"Compra com base em indicadores ajustados e pontuação {buy_score}"
        }

    # Decisão de venda
    if sell_score >= sell_threshold and asset_quantity >= min_asset_quantity and risk_manager.can_trade(asset, 'sell', float(quantity_to_sell), price, df):
        profit = calculate_profit(last_buy, price) if last_buy else 0
        last_sell = price
        logger.info(f"Venda com pontuação de {sell_score}/{sell_threshold}. Lucro: {profit*100:.2f}%")
        add_transaction(transactions, "sells", price)
        log_transaction_details("venda", asset, quantity_to_sell, price, profit)
        return {
            'asset': asset,
            'quantity': quantity_to_sell,
            'price': price,
            'type': 'sell',
            'reason': f"Venda com base em indicadores ajustados e pontuação {sell_score}"
        }

    # Se não houver condições favoráveis para compra ou venda, mantemos a posição
    logger.info(f"Posição mantida (Compra: {buy_score}, Venda: {sell_score}) para carteira madura.")
    return {
        'asset': asset,
        'quantity': 0,
        'price': price,
        'type': 'hold',
        'reason': "Hold - Estratégia de indicadores ajustados para carteira madura"
    }





def trading_decision(asset, price, portfolio_manager, df):
    global last_buy, last_sell
    asset_quantity = portfolio_manager.get_balance(asset.replace('USDT', ''))
    cash_balance = portfolio_manager.get_cash_balance()

    if asset_quantity < 0.96 or last_buy <= 0 or last_sell <= 0:
        return small_portfolio_strategy(asset, price, portfolio_manager, df)
    else:

        return small_portfolio_strategy(asset, price, portfolio_manager, df)