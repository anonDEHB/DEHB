import os
import sys
import json
import time
import pickle
import argparse
import numpy as np

from hpolib.benchmarks.surrogates.paramnet import SurrogateReducedParamNetTime

from dehb import DE
from dehb import DEHB, PDEHB

from multiprocessing.managers import BaseManager


# Common objective function for DE & DEHB representing SVM Surrogates benchmark
def f(config, budget=None):
    global max_budget, b
    if budget is not None:
        fitness = b.objective_function(config, budget=budget)
    else:
        fitness = b.objective_function(config)
        budget = max_budget
    fitness = fitness['function_value']
    time.sleep(float(budget or 0))
    cost = time.time()
    return fitness, cost


def calc_test_scores(history):
    global de, b
    valid_scores = []
    test_scores = []
    test_error = 1
    inc = np.inf
    for i in range(len(history)):
        valid_error = history[i][1]
        if valid_error < inc:
            inc = valid_error
            config = de.vector_to_configspace(history[i][0])
            res = b.objective_function_test(config)
            test_error = res['function_value']
        test_scores.append(test_error)
    return test_scores


def save_json(valid, test, runtime, output_path, run_id):
    res = {}
    res['validation_score'] = valid.tolist()
    res['test_score'] = test
    res['runtime'] = runtime.tolist()  # np.cumsum(runtime).tolist()
    fh = open(os.path.join(output_path, 'run_{}.json'.format(run_id)), 'w')
    json.dump(res, fh)
    fh.close()


def save_configspace(cs, path, filename='configspace'):
    fh = open(os.path.join(path, '{}.pkl'.format(filename)), 'wb')
    pickle.dump(cs, fh)
    fh.close()


parser = argparse.ArgumentParser()
parser.add_argument('--dataset', default='mnist', help="name of the dataset used",
                    choices=['adult', 'higgs', 'letter', 'mnist', 'optdigits', 'poker'])
parser.add_argument('--fix_seed', default='False', type=str, choices=['True', 'False'],
                    nargs='?', help='seed')
parser.add_argument('--run_id', default=0, type=int, nargs='?',
                    help='unique number to identify this run')
parser.add_argument('--runs', default=None, type=int, nargs='?', help='number of runs to perform')
parser.add_argument('--run_start', default=0, type=int, nargs='?',
                    help='run index to start with for multiple runs')
parser.add_argument('--brackets', default=None, type=int, nargs='?',
                    help='number of DEHB iterations')
parser.add_argument('--fevals', default=None, type=int, nargs='?',
                    help='number of function evaluations in total')
parser.add_argument('--total_cost', default=None, type=int, nargs='?',
                    help='total cost or budget for the complete DEHB run')
parser.add_argument('--output_path', default="./results", type=str, nargs='?',
                    help='specifies the path where the results will be saved')
strategy_choices = ['rand1_bin', 'rand2_bin', 'rand2dir_bin', 'best1_bin', 'best2_bin',
                    'currenttobest1_bin', 'randtobest1_bin',
                    'rand1_exp', 'rand2_exp', 'rand2dir_exp', 'best1_exp', 'best2_exp',
                    'currenttobest1_exp', 'randtobest1_exp']
parser.add_argument('--strategy', default="rand1_bin", choices=strategy_choices,
                    type=str, nargs='?',
                    help="specify the DE strategy from among {}".format(strategy_choices))
parser.add_argument('--mutation_factor', default=0.5, type=float, nargs='?',
                    help='mutation factor value')
parser.add_argument('--crossover_prob', default=0.5, type=float, nargs='?',
                    help='probability of crossover')
parser.add_argument('--n_workers', default=1, type=int, nargs='?',
                    help='number of workers to parellelize')
parser.add_argument('--eta', default=3, type=int, nargs='?',
                    help='SH parameter')
parser.add_argument('--verbose', action="store_true", help='to print progress or not')
parser.add_argument('--folder', default="pdehb", type=str, nargs='?',
                    help='name of folder where files will be dumped')


if __name__ == "__main__":
    args = parser.parse_args()
    args.fix_seed = True if args.fix_seed == 'True' else False

    folder = "{}/{}".format(args.dataset, args.folder)

    output_path = os.path.join(args.output_path, folder)
    os.makedirs(output_path, exist_ok=True)

    # Loading benchmark
    BaseManager.register('benchmark', SurrogateReducedParamNetTime)
    manager = BaseManager()
    manager.start()
    b = manager.benchmark(dataset=args.dataset)

    # Parameter space to be used by DE
    cs = b.get_configuration_space()
    dimensions = len(cs.get_hyperparameters())

    budgets = {  # (min, max)-budget (seconds) for the different data sets
        'adult': (9, 243),
        'higgs': (9, 243),
        'letter': (3, 81),
        'mnist': (9, 243),
        'optdigits': (1, 27),
        'poker': (81, 2187),
    }
    min_budget, max_budget = budgets[args.dataset]
    # min_budget, max_budget = (1, 9)

    # Initializing DE object
    dehb = PDEHB(cs=cs, dimensions=dimensions, f=f, strategy=args.strategy,
                mutation_factor=args.mutation_factor, crossover_prob=args.crossover_prob,
                eta=args.eta, min_budget=min_budget, max_budget=max_budget,
                n_workers=args.n_workers)

    # Helper DE object for vector to config mapping
    de = DE(cs=cs, b=b, f=f)

    if args.runs is None:  # for a single run
        if not args.fix_seed:
            np.random.seed(0)
        # Running DE iterations
        traj, runtime, history = dehb.run(
            fevals=args.fevals,
            brackets=args.brackets,
            total_cost=args.total_cost,
            verbose=args.verbose
        )
        test_scores = calc_test_scores(history)

        save_json(traj, test_scores, runtime, output_path, args.run_id)

    else:  # for multiple runs
        for run_id, _ in enumerate(range(args.runs), start=args.run_start):
            if not args.fix_seed:
                np.random.seed(run_id)
            if args.verbose:
                print("\nRun #{:<3}\n{}".format(run_id + 1, '-' * 8))
            # Running DE iterations
            traj, runtime, history = dehb.run(
                fevals=args.fevals,
                brackets=args.brackets,
                total_cost=args.total_cost,
                verbose=args.verbose
            )
            test_scores = calc_test_scores(history)

            save_json(traj, test_scores, runtime, output_path, run_id)

            if args.verbose:
                print("Run saved. Resetting...")
            # essential step to not accumulate consecutive runs

            dehb.reset()

    save_configspace(cs, output_path)
    manager.shutdown()
