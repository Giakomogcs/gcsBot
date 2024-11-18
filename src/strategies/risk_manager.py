from services.binance_client import get_consecutive_trades, client
from services.portfolio_manager import PortfolioManager
import pandas as pd
import logging

from services.transaction_manager import load_block_counts, save_block_counts

# Configuração do logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()

class RiskManager:
    def __init__(self, portfolio_manager, min_quantity=0.0001, max_consecutive_trades=5, max_price_increase=0.05, max_price_drop=0.05):
        self.portfolio_manager = portfolio_manager
        self.min_quantity = min_quantity
        self.max_consecutive_trades = max_consecutive_trades
        self.max_price_increase = max_price_increase
        self.max_price_drop = max_price_drop

    def calculate_average_price(self, symbol, transaction_type, recent_only=True, recent_limit=10):
        try:
            orders = client.get_all_orders(symbol=symbol, limit=100)
            relevant_orders = [
                order for order in orders 
                if isinstance(order, dict) and order.get('status') == 'FILLED' and order.get('side', '').lower() == transaction_type
            ]

            if recent_only and len(relevant_orders) > recent_limit:
                relevant_orders = relevant_orders[-recent_limit:]

            if relevant_orders:
                prices = [float(order['price']) for order in relevant_orders if 'price' in order]
                if not prices:
                    logger.warning("Nenhuma ordem relevante contém 'price'.")
                    return 0
                average_price = sum(prices) / len(prices)
                logger.debug(f"Preço médio calculado para {transaction_type} de {symbol}: {average_price:.2f}")
                return average_price
            else:
                logger.debug(f"Nenhuma ordem relevante encontrada para {transaction_type} de {symbol}.")
                return 0
        except Exception as e:
            logger.error(f"Erro ao calcular preço médio: {e}")
            return 0


    def calculate_average_price(self, symbol, transaction_type, recent_only=True, recent_limit=10):
        try:
            orders = client.get_all_orders(symbol=symbol, limit=100)
            relevant_orders = [
                order for order in orders 
                if isinstance(order, dict) and order.get('status') == 'FILLED' and order.get('side', '').lower() == transaction_type
            ]

            if recent_only and len(relevant_orders) > recent_limit:
                relevant_orders = relevant_orders[-recent_limit:]

            if relevant_orders:
                prices = [float(order['price']) for order in relevant_orders if 'price' in order]
                if not prices:
                    logger.warning("Nenhuma ordem relevante contém 'price'.")
                    return 0
                average_price = sum(prices) / len(prices)
                logger.debug(f"Preço médio calculado para {transaction_type} de {symbol}: {average_price:.2f}")
                return average_price
            else:
                logger.debug(f"Nenhuma ordem relevante encontrada para {transaction_type} de {symbol}.")
                return 0
        except Exception as e:
            logger.error(f"Erro ao calcular preço médio: {e}")
            return 0

    def determine_market_trend(self, df):
        try:
            if not isinstance(df, pd.DataFrame):
                logger.error(f"O objeto 'df' não é um DataFrame. Tipo recebido: {type(df)}. Valor: {df}")
                return 'neutral'

            if 'close' not in df.columns:
                logger.error(f"Coluna 'close' ausente no DataFrame. Colunas disponíveis: {df.columns}")
                return 'neutral'

            # Verifica se o DataFrame tem dados suficientes para calcular as médias móveis
            if len(df) < 50:
                logger.warning("Dados insuficientes no DataFrame para calcular médias móveis. Retornando tendência 'neutral'.")
                return 'neutral'

            # Calcula médias móveis
            short_ma = df['close'].rolling(window=10).mean().iloc[-1]
            long_ma = df['close'].rolling(window=50).mean().iloc[-1]
            long_term_ma = df['close'].rolling(window=200).mean().iloc[-1] if len(df) >= 200 else None

            if pd.isna(short_ma) or pd.isna(long_ma):
                logger.error("As médias móveis calculadas contêm valores NaN. Verifique o DataFrame.")
                return 'neutral'

            # Identifica a tendência baseada em médias móveis
            if short_ma > long_ma:
                if long_term_ma and short_ma > long_term_ma:
                    logger.debug(f"Tendência de longo prazo bullish confirmada (short_ma={short_ma:.2f}, long_term_ma={long_term_ma:.2f})")
                logger.debug(f"Tendência do mercado: bullish (short_ma={short_ma:.2f}, long_ma={long_ma:.2f})")
                return 'bullish'
            elif short_ma < long_ma:
                if long_term_ma and short_ma < long_term_ma:
                    logger.debug(f"Tendência de longo prazo bearish confirmada (short_ma={short_ma:.2f}, long_term_ma={long_term_ma:.2f})")
                logger.debug(f"Tendência do mercado: bearish (short_ma={short_ma:.2f}, long_ma={long_ma:.2f})")
                return 'bearish'
            else:
                logger.debug("Tendência do mercado: neutral")
                return 'neutral'
        except Exception as e:
            logger.error(f"Erro ao determinar tendência de mercado: {e}")
            return 'neutral'

    def adapt_max_consecutive_trades(self, market_trend):
        if market_trend == 'bearish':
            self.max_consecutive_trades = 7
        elif market_trend == 'bullish':
            self.max_consecutive_trades = 5
        else:
            self.max_consecutive_trades = 3

        logger.debug(f"Max consecutive trades ajustado para {self.max_consecutive_trades} com base na tendência de mercado '{market_trend}'")

        return self.max_consecutive_trades
    
    

    def can_trade(self, symbol, transaction_type, quantity, price, df):
        consecutive_sell_blocks, consecutive_buy_blocks = load_block_counts()

        try:
            # Verifica se o stop-loss ou take-profit geral está ativo
            stop_status = self.portfolio_manager.check_stop_loss_take_profit()
            if stop_status != 'continue':
                logger.info(f"Operação bloqueada devido ao status global: {stop_status}")
                return False

            # Verifica se a venda deixaria menos do que a quantidade mínima permitida
            if transaction_type == 'sell' and (self.portfolio_manager.get_balance(symbol.replace('USDT', '')) - quantity) < self.min_quantity:
                logger.info(f"Venda bloqueada: não podemos vender {quantity}, pois deixaria menos do que o mínimo permitido ({self.min_quantity}).")
                return False

            # Verifica se a compra comprometeria a reserva de caixa
            if transaction_type == 'buy' and self.portfolio_manager.get_cash_balance() < self.portfolio_manager.reserve_cash + (quantity * price):
                logger.info(f"Compra bloqueada: saldo insuficiente após manter a reserva de caixa necessária.")
                return False

            # Adapta o limite de transações consecutivas com base na tendência de mercado
            market_trend = self.determine_market_trend(df)
            self.adapt_max_consecutive_trades(market_trend)

            # Verifica o número de transações consecutivas
            consecutive_trades = get_consecutive_trades(symbol, transaction_type)
            if consecutive_trades >= self.max_consecutive_trades:
                if transaction_type == 'sell':
                    consecutive_sell_blocks += 1
                    consecutive_buy_blocks = 0
                if transaction_type == 'buy':
                    consecutive_buy_blocks += 1
                    consecutive_sell_blocks = 0
                save_block_counts(consecutive_sell_blocks, consecutive_buy_blocks)

                logger.info(f"Transação bloqueada: limite de {transaction_type}s consecutivas atingido ({self.max_consecutive_trades}).")
                return False

            # Calcula preço médio de transações recentes
            average_price = self.calculate_average_price(symbol, transaction_type, recent_only=(market_trend == 'bearish'))

            # Verifica condições de compra
            if transaction_type == 'buy':
                if average_price > 0 and price > average_price:
                    if market_trend != 'bullish':
                        logger.info(f"Compra bloqueada: preço atual ({price:.2f}) acima da média ({average_price:.2f}) em mercado não otimista.")
                        return False

                if average_price > 0 and (average_price - price) / average_price > self.max_price_increase:
                    logger.info(f"Compra bloqueada: queda excessiva detectada. Evitando pegar um 'falling knife'.")
                    return False

            # Verifica condições de venda
            if transaction_type == 'sell':
                if average_price > 0 and price < average_price and market_trend != 'bearish':
                    logger.info(f"Venda bloqueada: preço atual ({price:.2f}) abaixo da média ({average_price:.2f}) em mercado não pessimista.")
                    return False

                previous_close_price = self.portfolio_manager.get_previous_close_price(symbol)
                if previous_close_price > 0 and (previous_close_price - price) / previous_close_price > self.max_price_drop:
                    logger.info(f"Venda bloqueada: queda rápida detectada. Evitando venda durante pânico.")
                    return False

            # Se todas as condições foram atendidas
            logger.debug(f"Transação permitida para {transaction_type} de {symbol}. Quantidade: {quantity}, Preço: {price:.2f}")
            return True
        except Exception as e:
            logger.error(f"Erro ao determinar se a negociação pode ser feita: {e}")
            return False




