from services.binance_client import get_consecutive_trades, client
from services.portfolio_manager import PortfolioManager

class RiskManager:
    def __init__(self, portfolio_manager, min_quantity=0.001, max_consecutive_trades=5):
        self.portfolio_manager = portfolio_manager  # Instância do PortfolioManager
        self.min_quantity = min_quantity  # Quantidade mínima de ativo para manter no portfólio
        self.max_consecutive_trades = max_consecutive_trades  # Limite de transações consecutivas

    def calculate_average_price(self, symbol, transaction_type):
        """
        Calcula a média de preços de compra ou venda usando o histórico de transações da Binance.
        """
        # Obtenha as ordens do histórico para o símbolo
        orders = client.get_all_orders(symbol=symbol, limit=100)  # Ajuste o limite conforme necessário

        # Filtra as transações do tipo especificado
        relevant_orders = [order for order in orders if order['status'] == 'FILLED' and order['side'].lower() == transaction_type]

        # Calcula a média de preços
        if relevant_orders:
            prices = [float(order['price']) for order in relevant_orders]
            average_price = sum(prices) / len(prices)
            return average_price  # Retorna um valor numérico
        else:
            return 0  # Retorna 0 se não houver transações do tipo especificado


    def can_trade(self, symbol, transaction_type, quantity, price):
        """
        Determina se uma transação é permitida com base em quantidade mínima, transações consecutivas, média de preços
        e controle de stop loss/take profit.
        """
        # Verifica se o stop loss ou take profit foram atingidos
        stop_status = self.portfolio_manager.check_stop_loss_take_profit()
        if stop_status != 'continue':
            print(f"Operação bloqueada devido ao status: {stop_status}")
            return False

        # Verifica quantidade mínima para venda
        if transaction_type == 'sell' and quantity <= self.min_quantity:
            print("Quantidade insuficiente para venda. Operação ignorada.")
            return False

        # Verifica o limite de transações consecutivas
        consecutive_trades = get_consecutive_trades(symbol, transaction_type)
        if consecutive_trades >= self.max_consecutive_trades:
            print(f"Limite de {transaction_type}s consecutivas atingido. Operação ignorada.")
            return False

        # Verifica média de preços de transações anteriores
        average_price = self.calculate_average_price(symbol, transaction_type)
        if transaction_type == 'buy' and average_price > 0 and price > average_price:
            print(f"Preço de compra acima da média de compras ({average_price:.2f}). Aguardando queda para melhores oportunidades.")
            return False
        elif transaction_type == 'sell' and average_price > 0 and price < average_price:
            print(f"Preço atual abaixo da média de vendas ({average_price:.2f}). Esperando um valor melhor.")
            return False

        return True  # Permite a transação se todas as verificações forem aprovadas
