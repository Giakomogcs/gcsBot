from services.binance_client import get_consecutive_trades, client
from services.portfolio_manager import PortfolioManager
import pandas as pd
import logging

# Configuração do logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()

class RiskManager:
    def __init__(self, portfolio_manager, min_quantity=0.001, max_consecutive_trades=5, max_price_increase=0.05, max_price_drop=0.05):
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

    def determine_market_trend(self, df):
        try:
            if not isinstance(df, pd.DataFrame):
                logger.error(f"O objeto 'df' não é um DataFrame. Tipo recebido: {type(df)}. Valor: {df}")
                return 'neutral'

            if 'close' not in df.columns:
                logger.error(f"Coluna 'close' ausente no DataFrame. Colunas disponíveis: {df.columns}")
                return 'neutral'

            short_ma = df['close'].rolling(window=10).mean().iloc[-1]
            long_ma = df['close'].rolling(window=50).mean().iloc[-1]

            if pd.isna(short_ma) or pd.isna(long_ma):
                logger.error("As médias móveis calculadas contêm valores NaN. Verifique o DataFrame.")
                return 'neutral'

            if short_ma > long_ma:
                logger.debug(f"Tendência do mercado: bullish (short_ma={short_ma:.2f}, long_ma={long_ma:.2f})")
                return 'bullish'
            elif short_ma < long_ma:
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
            self.max_consecutive_trades = 3
        else:
            self.max_consecutive_trades = 5

        logger.debug(f"Max consecutive trades ajustado para {self.max_consecutive_trades} com base na tendência de mercado '{market_trend}'")

    def can_trade(self, symbol, transaction_type, quantity, price, df):
        try:
            stop_status = self.portfolio_manager.check_stop_loss_take_profit()
            if stop_status != 'continue':
                logger.info(f"Operação bloqueada devido ao status: {stop_status}")
                return False

            if transaction_type == 'sell' and (self.portfolio_manager.get_balance(symbol.replace('USDT', '')) - quantity) < self.min_quantity:
                logger.info("Operação de venda cancelada: reserva mínima de ativo não atingida.")
                return False

            if transaction_type == 'buy' and self.portfolio_manager.get_cash_balance() < self.portfolio_manager.reserve_cash + (quantity * price):
                logger.info("Operação de compra cancelada: saldo insuficiente para manter a reserva mínima de caixa.")
                return False

            market_trend = self.determine_market_trend(df)
            self.adapt_max_consecutive_trades(market_trend)

            consecutive_trades = get_consecutive_trades(symbol, transaction_type)
            if not isinstance(consecutive_trades, int):
                logger.error(f"consecutive_trades não é um inteiro: {consecutive_trades}")
                return False

            logger.debug(f"Transações consecutivas de tipo '{transaction_type}' para {symbol}: {consecutive_trades}")

            if consecutive_trades >= self.max_consecutive_trades:
                logger.info(f"Limite de {transaction_type}s consecutivas atingido. Operação ignorada.")
                return False

            average_price = self.calculate_average_price(symbol, transaction_type, recent_only=(market_trend == 'bearish'))

            if transaction_type == 'buy':
                if average_price > 0 and price > average_price:
                    if market_trend != 'bullish':
                        logger.info(f"Preço de compra acima da média de compras ({average_price:.2f}). Aguardando queda para melhores oportunidades.")
                        return False

                if average_price > 0 and (average_price - price) / average_price > self.max_price_increase:
                    logger.info(f"Queda excessiva detectada. Evitando comprar para não 'catching a falling knife'.")
                    return False

            if transaction_type == 'sell':
                if average_price > 0 and price < average_price and market_trend != 'bearish':
                    logger.info(f"Preço atual abaixo da média de vendas ({average_price:.2f}). Esperando um valor melhor.")
                    return False

                previous_close_price = self.portfolio_manager.get_previous_close_price(symbol)
                if previous_close_price > 0 and (previous_close_price - price) / previous_close_price > self.max_price_drop:
                    logger.info(f"Queda rápida detectada. Evitando vender durante pânico.")
                    return False

            logger.debug(f"Negociação permitida para {transaction_type} de {symbol} com quantidade {quantity} a preço {price:.2f}")
            return True
        except Exception as e:
            logger.error(f"Erro ao determinar se a negociação pode ser feita: {e}")
            return False
