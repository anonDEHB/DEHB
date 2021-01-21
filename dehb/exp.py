import sys
import time
import psutil
import numpy as np

import dask
from distributed import Client
from memory_profiler import profile

from multiprocessing.managers import BaseManager


# @profile
def dummyfunc(x):
    time.sleep(x)
    return time.time()


def is_workers_available(futures, client):
    if len(futures) >= sum(client.nthreads().values()):
        return False
    return True


# @profile
def run(client, runlen):
    global proc
    futures = []
    counter = 0
    while counter < runlen:
        if is_workers_available(futures, client):
            futures.append(client.submit(dummyfunc, counter))
            mem = proc.memory_info().rss / 1024 ** 2
            print("Parent #{:<2} - Mem: {:<.4f} MB".format(counter, mem))
            # print("Futures: {} - Client: {}".format(len(futures), sys.getsizeof(client)))
            counter += 1
        done_list = [future for future in futures if future.done()]
        futures = [future for future in futures if not future.done()]
    client.gather(futures)
    client.close()


if __name__ == "__main__":
    n_workers = 2
    runlen = 20
    client = Client(n_workers=n_workers, processes=True, threads_per_worker=1)
    BaseManager.register('proc', psutil.Process)
    manager = BaseManager()
    manager.start()
    # proc = psutil.Process()
    proc = manager.proc()
    run(client, runlen)
    manager.shutdown()
    print("Terminating...")
