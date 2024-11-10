import json
import os
from datetime import datetime

TRANSACTION_FILE = 'transaction_history.json'

def load_transactions():
    """Carrega o histórico de transações ou cria uma estrutura vazia com transações iniciais se o arquivo não existir."""
    if os.path.exists(TRANSACTION_FILE):
        with open(TRANSACTION_FILE, 'r') as file:
            return json.load(file)
    else:
        # Estrutura inicial com uma transação de compra e uma de venda com preços zerados e data atual
        transactions = {
            "buys": [{"price": 0.0, "time": datetime.now().timestamp()}],
            "sells": [{"price": 0.0, "time": datetime.now().timestamp()}]
        }
        save_transactions(transactions)  # Cria o arquivo com a estrutura inicial
        return transactions

def save_transactions(transactions):
    """Salva as transações no arquivo JSON."""
    with open(TRANSACTION_FILE, 'w') as file:
        json.dump(transactions, file)

def add_transaction(transactions, transaction_type, price):
    """Adiciona uma nova transação, mantendo somente as 5 mais recentes do tipo especificado.
    Substitui a transação mais antiga se estiver com o preço zerado.
    """
    transaction_data = {"price": price, "time": datetime.now().timestamp()}
    
    # Verifica se o primeiro item está com preço zerado
    if transactions[transaction_type] and transactions[transaction_type][0]['price'] == 0:
        # Substitui o primeiro item
        transactions[transaction_type][0] = transaction_data
    else:
        # Adiciona a nova transação ao final
        transactions[transaction_type].append(transaction_data)
        
        # Garante que mantém apenas as 5 transações mais recentes
        if len(transactions[transaction_type]) > 6:
            transactions[transaction_type].pop(0)
    
    # Salva as transações
    save_transactions(transactions)


def get_average_price(transactions, transaction_type):
    """Calcula a média dos preços das últimas 5 transações do tipo especificado."""
    prices = [t['price'] for t in transactions[transaction_type]]
    return sum(prices) / len(prices) if prices else None

def get_last_transaction(transactions, transaction_type):
    """Obtém o preço da última transação de compra ou venda, se houver."""
    if transactions.get(transaction_type):  # Verifica se existe uma lista para o tipo de transação
        return transactions[transaction_type][-1].get('price', 0)  # Retorna apenas o valor de 'price'
    return 0  # Retorna 0 se não houver transações do tipo solicitado


