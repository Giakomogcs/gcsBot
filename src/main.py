import sys
import os
import time
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.services.binance_client import get_realtime_price, get_historical_data, get_account_balance, execute_trade
from src.services.portfolio_manager import PortfolioManager
from src.services.transaction_logger import TransactionLogger
from src.strategies.basic_strategy import trading_decision

# Instanciar a carteira e o logger
portfolio_manager = PortfolioManager()
initial_balance = portfolio_manager.initial_balance
transaction_logger = TransactionLogger(initial_balance)

def realtime_trading_bot():
    asset = 'BTCUSDT'
    try:
        while True:
            # Obter o preço atual do ativo e exibir no console
            price = get_realtime_price(asset)
            print(f"Preço atual de {asset}: ${price:.2f}")

            # Exibir saldo atual da conta Binance
            balance_df = get_account_balance()
            if balance_df is not None:
                print("Saldo atual da carteira Binance:")
                print(balance_df)

            # Analisar dados históricos para decidir sobre negociação
            print(f"Analisando dados históricos para {asset}...")
            df = get_historical_data(asset)

            # Obter decisão de negociação
            decision = trading_decision(asset, price, portfolio_manager, df)

            # Execute a negociação se houver uma decisão de compra ou venda
            if decision['type'] in ['buy', 'sell']:
                print(f"Decisão: {decision['type'].upper()} {decision['quantity']} {asset} a ${decision['price']:.2f}")

                # Enviar ordem para a Binance
                execute_trade(decision['asset'], decision['quantity'], decision['type'].upper())

                # Atualizar o portfólio e registrar a transação
                portfolio_manager.update_balance(
                    asset=decision['asset'], 
                    quantity=decision['quantity'], 
                    price=decision['price'], 
                    transaction_type=decision['type']
                )
                transaction_logger.record_transaction(decision, portfolio_manager)
                print("Transação registrada no Excel.")
            else:
                print("Nenhuma transação realizada (hold).")

            # Pausa entre os ciclos
            print("Aguardando o próximo ciclo de verificação...\n")
            time.sleep(60)

    except KeyboardInterrupt:
        transaction_logger.export_to_excel()
        print("Bot finalizado e histórico salvo no Excel.")

if __name__ == "__main__":
    realtime_trading_bot()
