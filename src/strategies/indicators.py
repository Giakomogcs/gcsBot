import pandas as pd

def moving_average(series, period):
    if len(series) < period:
        return pd.Series([None] * len(series))  # Retorna série vazia se não houver dados suficientes
    return series.rolling(window=period).mean()
