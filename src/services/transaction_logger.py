import pandas as pd
from openpyxl import load_workbook
from datetime import datetime
import os

class TransactionLogger:
    def __init__(self, initial_balance):
        self.file_name = 'portfolio_history_detailed.xlsx'
        self.initial_balance = initial_balance  # Saldo inicial da carteira
        self.cumulative_profit_loss = 0  # Lucro/prejuízo acumulado

        # Cria o arquivo se ele não existir
        if not os.path.exists(self.file_name):
            self.create_initial_file()

    def create_initial_file(self):
        # Cria um DataFrame vazio com as colunas detalhadas apropriadas
        columns = [
            'date_time', 'asset', 'transaction_type', 'quantity', 'price_per_asset', 
            'transaction_total', 'reason', 'profit_loss', 'total_balance', 'asset_balance',
            'investment_usd', 'returned_to_cash_usd', 'cumulative_profit_loss',
            'usdt_balance', 'roi_percentage', 'cumulative_profit_loss_percentage'
        ]
        df = pd.DataFrame(columns=columns)
        df.to_excel(self.file_name, index=False)

    def record_transaction(self, transaction, portfolio_manager):
        # Obtém o nome do ativo principal (ex: de BTCUSDT extrai BTC)
        base_asset = transaction['asset'].replace('USDT', '')

        # Calcula lucro ou prejuízo com base na transação
        if transaction['type'] == 'sell':
            avg_cost = portfolio_manager.assets[base_asset]['average_cost']
            profit_loss = (transaction['price'] - avg_cost) * transaction['quantity']
            returned_to_cash = transaction['quantity'] * transaction['price']
            investment = 0  # Nenhum investimento em uma venda
        else:
            profit_loss = 0  # Em uma compra inicial, o lucro/prejuízo não é realizado
            returned_to_cash = 0  # Nada retornado ao saldo em uma compra
            investment = transaction['quantity'] * transaction['price']

        # Atualiza o lucro/prejuízo acumulado
        self.cumulative_profit_loss += profit_loss

        # Atualiza saldo total da carteira
        total_balance = portfolio_manager.cash_balance + sum(
            asset['quantity'] * asset['average_cost'] for asset in portfolio_manager.assets.values()
        )

        # Obtém o saldo atual do ativo base
        asset_balance = portfolio_manager.assets.get(base_asset, {}).get('quantity', 0)

        # Calcula ROI e porcentagem de lucro/prejuízo acumulado
        roi_percentage = ((total_balance - self.initial_balance) / self.initial_balance) * 100
        cumulative_profit_loss_percentage = (self.cumulative_profit_loss / self.initial_balance) * 100

        # Constrói a linha de dados detalhada
        data = {
            'date_time': datetime.now(),
            'asset': transaction['asset'],
            'transaction_type': transaction['type'],
            'quantity': f"{transaction['quantity']:.8f}",  # Quantidade exata da transação
            'price_per_asset': f"{transaction['price']:.2f}",  # Preço unitário em USDT por ativo
            'transaction_total': f"{transaction['quantity'] * transaction['price']:.2f}",  # Valor total da transação em USDT
            'reason': transaction['reason'],
            'profit_loss': f"{profit_loss:.2f}",
            'total_balance': f"{total_balance:.2f}",
            'asset_balance': f"{asset_balance:.8f}",
            'investment_usd': f"{investment:.2f}",
            'returned_to_cash_usd': f"{returned_to_cash:.2f}",
            'cumulative_profit_loss': f"{self.cumulative_profit_loss:.2f}",
            'usdt_balance': f"{portfolio_manager.cash_balance:.2f}",
            'roi_percentage': f"{roi_percentage:.2f}",
            'cumulative_profit_loss_percentage': f"{cumulative_profit_loss_percentage:.2f}"
        }
        
        # Converte a transação para DataFrame e adiciona ao Excel em tempo real
        df = pd.DataFrame([data])

        with pd.ExcelWriter(self.file_name, engine='openpyxl', mode='a', if_sheet_exists='overlay') as writer:
            df.to_excel(writer, index=False, header=False, startrow=writer.sheets['Sheet1'].max_row)
        
        print(f"Transação registrada: {data}")

    def export_to_excel(self):
        print(f"Transações registradas em tempo real no arquivo '{self.file_name}'.")
