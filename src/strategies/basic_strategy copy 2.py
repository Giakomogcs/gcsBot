import json
import os
from services.binance_client import get_consecutive_trades, get_recent_prices
from strategies.risk_manager import RiskManager
from services.transaction_manager import get_last_transaction_time, load_transactions, save_transactions, add_transaction, get_average_price, get_last_transaction
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


def calculate_indicators(df, short_ma_period=10, long_ma_period=150, rsi_period=12, volume_threshold=1.1):
    if len(df) < max(short_ma_period, long_ma_period):
        logger.warning("Dados insuficientes para calcular todos os indicadores. Aguardando mais dados...")
        return None, None, None, None, None, None

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
    """Formata a quantidade para 8 casas decimais, sem notação científica."""
    return "{:.8f}".format(quantity)

def log_transaction_details(transaction_type, asset, quantity, price, profit=None):
    if profit is not None:
        logger.info(f"{transaction_type.capitalize()} realizado para {asset}. Quantidade: {quantity}, Preço: {price}, Lucro: {profit}")
    else:
        logger.info(f"{transaction_type.capitalize()} realizado para {asset}. Quantidade: {quantity}, Preço: {price}")

def calculate_profit(last_price, current_price):
    return (current_price - last_price) / last_price

def small_portfolio_strategy(asset, price, portfolio_manager, df, max_consecutive_sells=3, max_consecutive_buys=3):
    global last_buy, last_sell

    risk_manager = RiskManager(portfolio_manager)
    cash_balance = float(portfolio_manager.get_cash_balance())
    asset_quantity = float(portfolio_manager.get_balance(asset.replace('USDT', '')))
    price = float(price)

    consecutive_sells = get_consecutive_trades(asset, 'sell')
    consecutive_buys = get_consecutive_trades(asset, 'buy')

    MIN_PROFIT_PERCENTAGE = 0.0015  # 0,25% de lucro
    STOP_LOSS_PERCENTAGE = 0.0018  # 0,4% de perda


    # Limite de tempo para vendas recentes
    max_time_diff = timedelta(hours=12)
    # Obtém o horário da última venda
    last_sell_time = get_last_transaction_time(transactions, 'sells')
    
    recent_sell = False
    if last_sell_time:
        last_sell_time = datetime.fromtimestamp(int(last_sell_time))
        recent_sell = (datetime.now() - last_sell_time) <= max_time_diff

    # Verifica o horário da última compra
    last_buy_time = get_last_transaction_time(transactions, 'buys')

    recent_buy = False
    if last_buy_time:
        last_buy_time = datetime.fromtimestamp(int(last_buy_time))
        recent_buy = (datetime.now() - last_buy_time) <= max_time_diff

    print(f"recent_sell={recent_sell}, recent_buy={recent_buy}")


    # Condições adicionais baseadas nas médias curtas
    average_buy_price = get_average_price(transactions, "buys")
    average_sell_price = get_average_price(transactions, "sells")

    # Definindo target_sell_price e target_buy_price com verificação inicial de recent_sell e recent_buy
    if not recent_sell or not recent_buy:
        target_sell_price = 0
        target_buy_price = 0
    else:
        # Definindo target_sell_price
        if average_buy_price > 0 and last_buy > 0:
            target_sell_price = average_buy_price * (1 + MIN_PROFIT_PERCENTAGE)
        elif last_buy > 0:
            target_sell_price = last_buy * (1 + MIN_PROFIT_PERCENTAGE)
        else:
            target_sell_price = 0

        # Definindo target_buy_price
        if average_sell_price > 0 and last_sell > 0:
            target_buy_price = average_sell_price * (1 - 2 * STOP_LOSS_PERCENTAGE)
        elif last_sell > 0:
            target_buy_price = last_sell * (1 - 2 * STOP_LOSS_PERCENTAGE)
        else:
            target_buy_price = 0


    # Lógica para as variáveis booleanas broke ice
    if target_buy_price == 0 and average_sell_price > price:
        buy_broke_cold = True
        sell_broke_cold = False
        logger.info("Condição buy_broke_cold atendida: average_sell_price é maior que o preço atual")
    elif target_sell_price == 0 and average_buy_price < price:
        sell_broke_cold = True
        buy_broke_cold = False
        logger.info("Condição sell_broke_cold atendida: average_buy_price é menor que o preço atual")
    else:
        buy_broke_cold = False
        sell_broke_cold = False
        logger.info("Nenhuma condição 'broke cold' atendida.")

    # Logs para verificar as condições finais
    logger.info(f"buy_broke_cold: {buy_broke_cold}, sell_broke_cold: {sell_broke_cold}")
    logger.info(f"target_buy_price: {target_buy_price}, target_sell_price: {target_sell_price}")


    # Integração com get_recent_prices para obter média de curto prazo se não houver histórico suficiente
    if (average_buy_price <= 0 or last_buy <= 0 or not last_buy_time) and not buy_broke_cold:
        logger.info("Nenhum registro recente de compra disponível no JSON. Usando média de preços recentes.")
        average_buy_price = get_recent_prices(asset)

    elif (average_sell_price <= 0 or last_sell <= 0 or not last_sell_time) and not sell_broke_cold:
        logger.info("Nenhum registro recente de venda disponível no JSON. Usando média de preços recentes.")
        average_sell_price = get_recent_prices(asset)


    logger.info("Estratégia Small Portfolio ativada.")
    logger.info(f"Condições de compra: target_buy_price={target_buy_price}, recent_sell={recent_sell}, consecutive_buys={consecutive_buys}")

    # Obter os indicadores e verificar a validade
    short_ma, long_ma, rsi, volume_filter, _, _ = calculate_indicators(df)
    logger.info(f"Indicadores: short_ma={short_ma}, long_ma={long_ma}, rsi={rsi}, volume_filter={volume_filter}")

    if None in (short_ma, long_ma, rsi, volume_filter):
        logger.warning("Indicadores insuficientes para tomar decisão de compra/venda.")
        return {
            'asset': asset,
            'quantity': 0,
            'price': price,
            'type': 'hold',
            'reason': "Hold - Dados insuficientes para indicadores"
        }

    # Condições de compra aprimoradas
    if consecutive_buys < max_consecutive_buys:
        if short_ma < long_ma * 0.995 or rsi < 50 or (recent_sell and price <= target_buy_price) or buy_broke_cold and not sell_broke_cold:
            quantity_to_buy = min((cash_balance * portfolio_manager.get_investment_percentage()) / price, 
                                  portfolio_manager.get_investment_percentage() * asset_quantity)
            quantity_to_buy = format_quantity(max(quantity_to_buy, min_asset_quantity))

            logger.info(f"Valores de compra: quantity_to_buy={quantity_to_buy}, price={price}, cash_balance={cash_balance}")
            if float(quantity_to_buy) >= min_asset_quantity and risk_manager.can_trade(asset, 'buy', float(quantity_to_buy), price, df):
                add_transaction(transactions, "buys", price)
                logger.info("Condições de compra atendidas. Executando compra.")
                log_transaction_details("compra", asset, quantity_to_buy, price)
                return {
                    'asset': asset,
                    'quantity': float(quantity_to_buy),
                    'price': price,
                    'type': 'buy',
                    'reason': "Compra em oportunidade de curto prazo com base em indicadores e limite de compras consecutivas"
                }
        else:
            logger.info("Condições de compra não atendidas. Valores atuais: "
                        f"short_ma={short_ma}, long_ma={long_ma}, rsi={rsi}, price={price}, target_buy_price={target_buy_price}")
    else:
        logger.info(f"Condição de vompra não atingida: Limite de quantidade de compras")

    # Condições de venda
    if consecutive_sells < max_consecutive_sells:
        if price >= target_sell_price or not buy_broke_cold and sell_broke_cold:
            quantity_to_sell = min(asset_quantity * portfolio_manager.get_investment_percentage(), asset_quantity - min_asset_quantity)
            quantity_to_sell = format_quantity(max(quantity_to_sell, min_asset_quantity))

            logger.info(f"Valores de venda: quantity_to_sell={quantity_to_sell}, price={price}, asset_quantity={asset_quantity}")
            if float(quantity_to_sell) >= min_asset_quantity and risk_manager.can_trade(asset, 'sell', float(quantity_to_sell), price, df):
                profit = calculate_profit(last_buy, price) if last_buy else 0
                add_transaction(transactions, "sells", price)
                logger.info(f"Venda realizada com lucro de {profit*100:.2f}%.")
                log_transaction_details("venda", asset, quantity_to_sell, price, profit)
                return {
                    'asset': asset,
                    'quantity': float(quantity_to_sell),
                    'price': price,
                    'type': 'sell',
                    'reason': "Venda para lucro a curto prazo em carteira pequena com limite de vendas consecutivas"
                }
        else:
            logger.info(f"Condição de venda não atingida: preço atual ({price}) >= preço-alvo ({target_sell_price}).")
    else:
        logger.info(f"Condição de venda não atingida: Limite de quantidade de vendas")

    logger.info("Nenhuma transação realizada para carteira pequena.")
    return {
        'asset': asset,
        'quantity': 0,
        'price': price,
        'type': 'hold',
        'reason': "Hold - Estratégia de acúmulo em carteira pequena"
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