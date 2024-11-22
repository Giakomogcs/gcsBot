import pandas as pd

def calculate_sma(data: pd.DataFrame, period: int, price_column: str = "close") -> pd.Series:
    """
    Calcula a Média Móvel Simples (SMA) para o período especificado.
    
    :param data: DataFrame com dados históricos de preços.
    :param period: Período para a SMA.
    :param price_column: Coluna do preço a ser usada (padrão: "close").
    :return: Série com os valores da SMA.
    """
    return data[price_column].rolling(window=period).mean()

def calculate_rsi(data: pd.DataFrame, period: int = 14, price_column: str = "close") -> pd.Series:
    """
    Calcula o Índice de Força Relativa (RSI) para o período especificado.
    
    :param data: DataFrame com dados históricos de preços.
    :param period: Período para o RSI.
    :param price_column: Coluna do preço a ser usada (padrão: "close").
    :return: Série com os valores do RSI.
    """
    delta = data[price_column].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi
