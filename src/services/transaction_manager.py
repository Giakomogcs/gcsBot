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

def get_last_transaction_time(transactions, transaction_type):
    """Obtém o horário (timestamp) da última transação de compra ou venda, se houver."""
    if transactions.get(transaction_type):  # Verifica se existe uma lista para o tipo de transação
        return transactions[transaction_type][-1].get('time', 0)  # Retorna apenas o valor de 'time'
    return 0  # Retorna 0 se não houver transações do tipo solicitado

from datetime import datetime

def clean_transactions_outside_market_average(transactions, MARKET_AVERAGE, THRESHOLD_FACTOR, recent_sell, recent_buy, price):
    """
    Remove transações do histórico se a média de preços de compra ou venda estiver muito
    abaixo ou muito acima da média do mercado.
    """
    # Calcula a média de compras e vendas no histórico
    average_buy_price = get_average_price(transactions, 'buys')
    average_sell_price = get_average_price(transactions, 'sells')
    
    # Verifica se a média de compras está muito abaixo ou acima da média do mercado
    if average_buy_price:
        if average_buy_price < MARKET_AVERAGE * THRESHOLD_FACTOR:
            transactions['buys'] = [{"price": 0.0, "time": datetime.now().timestamp()}]  # Limpa todas as transações de compra
            print("Histórico de compras muito abaixo da média do mercado. Transações de compra foram limpas.")
        elif average_buy_price > MARKET_AVERAGE / THRESHOLD_FACTOR:
            transactions['buys'] = [{"price": 0.0, "time": datetime.now().timestamp()}]  # Limpa todas as transações de compra
            print("Histórico de compras muito acima da média do mercado. Transações de compra foram limpas.")

    if not recent_buy:
        transactions['buys'] = [{"price": 0.0, "time": datetime.now().timestamp()}]  # Limpa todas as transações de compra
        print("Histórico de compras desatualizado. Transações de compra foram limpas.")


    
    # Verifica se a média de vendas está muito abaixo ou acima da média do mercado
    if average_sell_price:
        if average_sell_price < MARKET_AVERAGE * THRESHOLD_FACTOR:
            transactions['sells'] = [{"price": 0.0, "time": datetime.now().timestamp()}]  # Limpa todas as transações de venda
            print("Histórico de vendas muito abaixo da média do mercado. Transações de venda foram limpas.")
        elif average_sell_price > MARKET_AVERAGE / THRESHOLD_FACTOR:
            transactions['sells'] = [{"price": 0.0, "time": datetime.now().timestamp()}]  # Limpa todas as transações de venda
            print("Histórico de vendas muito acima da média do mercado. Transações de venda foram limpas.")

    if not recent_sell :
        transactions['sells'] = [{"price": 0.0, "time": datetime.now().timestamp()}]  # Limpa todas as transações de venda
        print("Histórico de vendas desatualizado. Transações de venda foram limpas.")
    
    # Salva o JSON atualizado após a limpeza
    save_transactions(transactions)







def load_block_counts():
    """Carrega as contagens de bloqueios consecutivos de compra e venda a partir do arquivo JSON.
    Cria o arquivo com valores iniciais se ele não existir.
    """
    if not os.path.exists("block_counts.json"):
        # Valores iniciais para os blocos de contagem
        counts = {"consecutive_sell_blocks": 0, "consecutive_buy_blocks": 0}
        
        # Cria o arquivo com os valores iniciais
        with open("block_counts.json", "w") as file:
            json.dump(counts, file)
            
        return 0, 0
    
    # Carrega os valores existentes do arquivo
    with open("block_counts.json", "r") as file:
        counts = json.load(file)
        return counts.get("consecutive_sell_blocks", 0), counts.get("consecutive_buy_blocks", 0)

def save_block_counts(consecutive_sell_blocks, consecutive_buy_blocks):
    """Salva as contagens de bloqueios consecutivos de compra e venda no arquivo JSON."""
    with open("block_counts.json", "w") as file:
        json.dump({
            "consecutive_sell_blocks": consecutive_sell_blocks,
            "consecutive_buy_blocks": consecutive_buy_blocks
        }, file)

