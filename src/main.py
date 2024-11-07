import sys
import os
import time
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.services.binance_client import get_realtime_price, get_historical_data, execute_trade
from src.services.portfolio_manager import PortfolioManager
from src.services.transaction_logger import TransactionLogger
from src.strategies.basic_strategy import trading_decision

# Instancia o gerenciador de portfólio e o logger de transações
portfolio_manager = PortfolioManager()
transaction_logger = TransactionLogger(initial_balance=portfolio_manager.initial_balance)

def realtime_trading_bot():
    asset = 'BTCUSDT'
    try:
        while True:
            # Obter o preço atual do ativo e exibir no console
            price = get_realtime_price(asset)
            print(f"Preço atual de {asset}: ${price:.2f}")

            # Exibir saldo atualizado da carteira (mantido pelo PortfolioManager)
            print("Saldo atual da carteira:")
            balance_df = portfolio_manager.balance_df  # Atualiza apenas se necessário
            print(balance_df)

            # Analisar dados históricos e obter decisão de negociação
            print(f"Analisando dados históricos para {asset}...")
            df = get_historical_data(asset)
            decision = trading_decision(asset, price, portfolio_manager, df)

            # Executar a negociação com base na decisão (compra/venda) e atualizar o portfólio
            if decision['type'] in ['buy', 'sell']:
                print(f"Decisão: {decision['type'].upper()} {decision['quantity']} {asset} a ${decision['price']:.2f}")
                
                # Tenta executar a ordem na Binance e registra a transação
                if execute_trade(decision['asset'], decision['quantity'], decision['type'].upper()):
                    portfolio_manager.update_balance(
                        asset=decision['asset'], 
                        quantity=decision['quantity'], 
                        price=decision['price'], 
                        transaction_type=decision['type']
                    )
                    transaction_logger.record_transaction(decision, portfolio_manager)
                    print("Transação registrada no histórico.")
                else:
                    print("Erro ao executar a transação na Binance.")

            else:
                print("Nenhuma transação realizada (hold).")

            # Pausa entre os ciclos de verificação
            print("Aguardando o próximo ciclo de verificação...\n")
            time.sleep(10)

    except KeyboardInterrupt:
        transaction_logger.export_to_excel()
        print("Bot finalizado e histórico salvo no Excel.")

if __name__ == "__main__":
    realtime_trading_bot()
