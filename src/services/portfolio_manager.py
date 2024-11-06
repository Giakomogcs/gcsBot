from src.services.binance_client import get_account_balance

class PortfolioManager:
    def __init__(self, stop_loss=0.05, take_profit=0.1, investor_profile='moderado'):
        # Inicializa o balance_df com os dados de saldo da Binance
        self.balance_df = get_account_balance()
        
        # Configurações iniciais de saldo de caixa e ativos
        usdt_balance = self.balance_df[self.balance_df['asset'] == 'USDT']['free'].values
        self.initial_balance = usdt_balance[0] if len(usdt_balance) > 0 else 0.0
        self.cash_balance = self.initial_balance
        
        # Inicializa os ativos com as quantidades e custos médios
        self.assets = {}
        for _, row in self.balance_df.iterrows():
            asset = row['asset']
            free_quantity = row['free']
            if free_quantity > 0 and asset != 'USDT':  # Exclui USDT do saldo de ativos
                self.assets[asset] = {'quantity': free_quantity, 'average_cost': 0}

        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.investor_profile = investor_profile

    def get_investment_percentage(self):
        if self.investor_profile == 'conservador':
            return 0.05  # 5%
        elif self.investor_profile == 'moderado':
            return 0.10  # 10%
        elif self.investor_profile == 'arrojado':
            return 0.20  # 20%
        else:
            raise ValueError("Perfil de investidor inválido. Escolha 'conservador', 'moderado' ou 'arrojado'.")

    def get_balance(self, asset):
        """Retorna o saldo do ativo específico."""
        if 'balance_df' not in self.__dict__ or self.balance_df is None:
            self.balance_df = get_account_balance()  # Atualiza o saldo se não estiver disponível
        balance_row = self.balance_df[self.balance_df['asset'] == asset]
        if not balance_row.empty:
            return balance_row.iloc[0]['free']
        return 0.0  # Retorna 0 se o ativo não estiver presente

    def update_balance(self, asset, quantity, price, transaction_type):
        cost = quantity * price
        if transaction_type == 'buy' and self.cash_balance >= cost:
            self.cash_balance -= cost
            if asset not in self.assets:
                self.assets[asset] = {'quantity': 0, 'average_cost': 0}
            total_quantity = self.assets[asset]['quantity'] + quantity
            self.assets[asset]['average_cost'] = ((self.assets[asset]['quantity'] * self.assets[asset]['average_cost']) + cost) / total_quantity
            self.assets[asset]['quantity'] = total_quantity
        elif transaction_type == 'sell' and asset in self.assets and self.assets[asset]['quantity'] >= quantity:
            self.cash_balance += cost
            self.assets[asset]['quantity'] -= quantity
            if self.assets[asset]['quantity'] <= 0:
                del self.assets[asset]
