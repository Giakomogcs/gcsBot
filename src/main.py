import sys
import os
import time
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.services.binance_client import get_realtime_price, get_historical_data, execute_trade
from src.services.transaction_manager import get_last_transaction, load_transactions, save_transactions, add_transaction, get_average_price
from src.services.portfolio_manager import PortfolioManager
from src.services.transaction_logger import TransactionLogger
from src.strategies.basic_strategy import trading_decision

# Configuração do logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()

# Instancia o gerenciador de portfólio e o logger de transações
portfolio_manager = PortfolioManager()
transaction_logger = TransactionLogger(initial_balance=portfolio_manager.initial_balance)

# Carrega as transações salvas
transactions = load_transactions()


save_transactions(transactions)  # Garante que o arquivo JSON é criado ao iniciar

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), retry=retry_if_exception_type(ConnectionError))
async def safe_get_realtime_price(asset, executor):
    """Obtém o preço atual do ativo de forma segura, com tentativas automáticas em caso de falha."""
    return await asyncio.get_event_loop().run_in_executor(executor, get_realtime_price, asset)

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), retry=retry_if_exception_type(ConnectionError))
async def safe_get_historical_data(asset, executor):
    """Obtém os dados históricos do ativo de forma segura, com tentativas automáticas em caso de falha."""
    return await asyncio.get_event_loop().run_in_executor(executor, get_historical_data, asset)

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), retry=retry_if_exception_type(ConnectionError))
async def safe_execute_trade(asset, quantity, side, executor):
    """Executa a ordem de trade de forma segura, com tentativas automáticas em caso de falha."""
    return await asyncio.get_event_loop().run_in_executor(executor, execute_trade, asset, quantity, side)

async def realtime_trading_bot():
    asset = 'BTCUSDT'
    executor = ThreadPoolExecutor(max_workers=3)


    try:
        while True:
            # Exibir saldo atual de BTC e USD
            btc_balance = portfolio_manager.get_balance('BTC')
            usdt_balance = portfolio_manager.get_cash_balance()
            logger.info(f"Saldo atual: {btc_balance:.6f} BTC, ${usdt_balance:.2f} USDT")

            # Obter o preço atual do ativo
            try:
                price = await safe_get_realtime_price(asset, executor)
                if price is None:
                    logger.warning(f"Não foi possível obter o preço atual para {asset}. Tentando novamente...")
                    await asyncio.sleep(5)
                    continue
                logger.info(f"Preço atual de {asset}: ${price:.2f}")
            except Exception as e:
                logger.error(f"Erro ao obter preço em tempo real após várias tentativas: {e}")
                await asyncio.sleep(10)
                continue

            # Analisar dados históricos
            try:
                logger.info(f"Analisando dados históricos para {asset}...")
                df = await safe_get_historical_data(asset, executor)
                if df is None or df.empty:
                    logger.warning("Dados históricos não disponíveis ou DataFrame vazio. Tentando novamente em breve...")
                    await asyncio.sleep(10)
                    continue
            except Exception as e:
                logger.error(f"Erro ao obter dados históricos após várias tentativas: {e}")
                await asyncio.sleep(10)
                continue

            # Obter decisão de negociação
            try:
                decision = trading_decision(asset, price, portfolio_manager, df)
                if not isinstance(decision, dict):
                    logger.error(f"A decisão retornada não é um dicionário. Valor recebido: {decision}")
                    await asyncio.sleep(10)
                    continue
            except Exception as e:
                logger.error(f"Erro ao calcular decisão de negociação: {e}")
                await asyncio.sleep(10)
                continue

            # Executar a negociação com base na decisão
            if decision.get('type') in ['buy', 'sell']:
                logger.info(f"Decisão: {decision['type'].upper()} {decision['quantity']} {asset} a ${decision['price']:.2f}")
                try:
                    result = await safe_execute_trade(decision['asset'], decision['quantity'], decision['type'].upper(), executor)
                    if result:
                        # Registrar transação nas listas de 5 últimos
                        add_transaction(transactions, 'buys' if decision['type'] == 'buy' else 'sells', decision['price'])

                        # Atualizar portfólio e salvar transações
                        portfolio_manager.update_balance(
                            asset=decision['asset'],
                            quantity=decision['quantity'],
                            price=decision['price'],
                            transaction_type=decision['type']
                        )
                        save_transactions(transactions)  # Salva as transações atualizadas
                        transaction_logger.record_transaction(decision, portfolio_manager, {"price": decision['price']})
                        logger.info("Transação registrada no histórico.")
                    else:
                        logger.error("Erro ao executar a transação na Binance após várias tentativas.")
                except Exception as e:
                    logger.error(f"Erro ao executar ordem após várias tentativas: {e}")
            else:
                logger.info("Nenhuma transação realizada (hold).")

            # Pausa entre os ciclos de verificação
            logger.info("Aguardando o próximo ciclo de verificação...\n")
            await asyncio.sleep(10)

    except asyncio.CancelledError:
        logger.info("Cancelamento detectado. Finalizando o bot com segurança...")
    except KeyboardInterrupt:
        logger.info("Interrupção do usuário detectada. Finalizando o bot...")
    except Exception as e:
        logger.critical(f"Erro inesperado no bot: {e}. Tentando reiniciar o bot em 30 segundos...")
        await asyncio.sleep(30)
        await realtime_trading_bot()
    finally:
        transaction_logger.export_to_excel()
        logger.info("Histórico salvo no Excel.")
        executor.shutdown(wait=True)
        logger.info("ThreadPoolExecutor encerrado.")

if __name__ == "__main__":
    try:
        asyncio.run(realtime_trading_bot())
    except KeyboardInterrupt:
        logger.info("Bot finalizado pelo usuário.")
