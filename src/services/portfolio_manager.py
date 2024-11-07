from src.services.binance_client import get_account_balance

class PortfolioManager:
    def __init__(self, stop_loss=0.08, take_profit=0.2, investor_profile='moderado', reserve_cash=100):
        # Inicializa o balance_df com os dados de saldo da Binance
        self.balance_df = get_account_balance()
        
        # Configurações iniciais de saldo de caixa e ativos
        usdt_balance = self.balance_df[self.balance_df['asset'] == 'USDT']['free'].values
        self.initial_balance = usdt_balance[0] if len(usdt_balance) > 0 else 0.0
        self.cash_balance = self.initial_balance
        self.reserve_cash = reserve_cash  # Quantia mínima de segurança para saldo de caixa

        # Inicializa os ativos com as quantidades e custos médios
        self.assets = {}
        for _, row in self.balance_df.iterrows():
            asset = row['asset']
            free_quantity = row['free']
            if free_quantity > 0 and asset != 'USDT':  # Exclui USDT do saldo de ativos
                self.assets[asset] = {'quantity': free_quantity, 'average_cost': 0}

        # Parâmetros de controle
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.investor_profile = investor_profile
        self.profit_loss_cumulative = 0  # Controle de ganhos/perdas acumuladas

    def get_investment_percentage(self):
        """Define o percentual de investimento com base no perfil do investidor."""
        balance = self.cash_balance
        if balance < 200:
            return 0.03  # 3% para carteiras pequenas
        elif balance < 2000:
            return 0.07  # 7% para carteiras médias
        else:
            return 0.15  # 15% para carteiras grandes

    def get_cash_balance(self):
        """Retorna o saldo de caixa atual, considerando a reserva mínima de segurança."""
        return max(0, self.cash_balance - self.reserve_cash)

    def get_balance(self, asset):
        """Retorna a quantidade disponível de um ativo específico no portfólio."""
        return self.assets.get(asset, {}).get('quantity', 0.0)

    def update_balance(self, asset, quantity, price, transaction_type):
        """Atualiza o saldo e controla ganhos/perdas com base no tipo de transação."""
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
            profit_loss = (price - self.assets[asset]['average_cost']) * quantity
            self.profit_loss_cumulative += profit_loss  # Atualiza lucro/prejuízo acumulado

            # Remove o ativo se a quantidade for zero
            if self.assets[asset]['quantity'] <= 0:
                del self.assets[asset]

        # Atualiza o perfil do investidor com base no desempenho recente
        self.update_investor_profile()

    def check_stop_loss_take_profit(self):
        """Verifica se o lucro ou perda acumulados atingiram o stop loss ou take profit."""
        if self.profit_loss_cumulative <= -self.initial_balance * self.stop_loss:
            print("Stop loss atingido. Pausando operações.")
            return 'stop_loss'
        elif self.profit_loss_cumulative >= self.initial_balance * self.take_profit:
            print("Take profit atingido. Pausando operações.")
            return 'take_profit'
        return 'continue'  # Continua operando caso os limites não sejam atingidos

    def update_investor_profile(self):
        """Atualiza o perfil de investidor com base nos resultados acumulados e no tamanho da carteira."""
        if self.profit_loss_cumulative >= self.initial_balance * 0.15:
            # Aumenta a agressividade do perfil se os lucros acumulados forem altos
            if self.investor_profile == 'conservador':
                self.investor_profile = 'moderado'
            elif self.investor_profile == 'moderado':
                self.investor_profile = 'arrojado'
            print(f"Perfil atualizado para {self.investor_profile} devido a desempenho positivo.")
        elif self.profit_loss_cumulative <= -self.initial_balance * 0.05:
            # Reduz a agressividade do perfil se as perdas acumuladas forem significativas
            if self.investor_profile == 'arrojado':
                self.investor_profile = 'moderado'
            elif self.investor_profile == 'moderado':
                self.investor_profile = 'conservador'
            print(f"Perfil atualizado para {self.investor_profile} devido a desempenho negativo.")
