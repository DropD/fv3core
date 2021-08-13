#!/usr/bin/env python3

import copy
import json
from argparse import Namespace
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np
from mpi4py import MPI


def set_experiment_info(
    experiment_name: str, time_step: int, backend: str, git_hash: str
) -> Dict[str, Any]:
    experiment: Dict[str, Any] = {}
    now = datetime.now()
    dt_string = now.strftime("%d/%m/%Y %H:%M:%S")
    experiment["setup"] = {}
    experiment["setup"]["timestamp"] = dt_string
    experiment["setup"]["dataset"] = experiment_name
    experiment["setup"]["timesteps"] = time_step
    experiment["setup"]["hash"] = git_hash
    experiment["setup"]["version"] = "python/" + backend
    experiment["setup"]["format_version"] = 2
    experiment["times"] = {}
    return experiment


def collect_keys_from_data(times_per_step: List[Dict[str, float]]) -> List[str]:
    """Collects all the keys in the list of dics and returns a sorted version"""
    keys = set()
    for data_point in times_per_step:
        for k, _ in data_point.items():
            keys.add(k)
    sorted_keys = list(keys)
    sorted_keys.sort()
    return sorted_keys


def put_data_into_dict(
    times_per_step: List[Dict[str, float]], results: Dict[str, Any]
) -> Dict[str, Any]:
    keys = collect_keys_from_data(times_per_step)
    data: List[float] = []
    for timer_name in keys:
        data.clear()
        for data_point in times_per_step:
            if timer_name in data_point:
                data.append(data_point[timer_name])
            results["times"][timer_name]["times"] = copy.deepcopy(data)
    return results


def gather_timing_data(
    times_per_step: List[Dict[str, float]],
    results: Dict[str, Any],
    comm: MPI.Comm,
    root: int = 0,
) -> Dict[str, Any]:
    """
    returns an updated version of  the results dictionary owned
    by the root node to hold data on the substeps as well as the main loop timers
    """
    is_root = comm.Get_rank() == root
    keys = collect_keys_from_data(times_per_step)
    data: List[float] = []
    for timer_name in keys:
        data.clear()
        for data_point in times_per_step:
            if timer_name in data_point:
                data.append(data_point[timer_name])

        sendbuf = np.array(data)
        recvbuf = None
        if is_root:
            recvbuf = np.array([data] * comm.Get_size())
        comm.Gather(sendbuf, recvbuf, root=0)
        if is_root:
            results["times"][timer_name]["times"] = copy.deepcopy(recvbuf.tolist())
    return results


def write_global_timings(backend, disabled_halos, experiment: Dict[str, Any]) -> None:
    now = datetime.now()
    halo_str = "nohalos" if disabled_halos else ""
    filename = now.strftime("%Y-%m-%d-%H-%M-%S")
    with open(filename + backend + halo_str + ".json", "w") as outfile:
        json.dump(experiment, outfile, sort_keys=True, indent=4)


def gather_hit_counts(
    hits_per_step: List[Dict[str, int]], results: Dict[str, Any]
) -> Dict[str, Any]:
    """collects the hit count across all timers called in a program execution"""
    for data_point in hits_per_step:
        for name, value in data_point.items():
            if name not in results["times"]:
                print(name)
                results["times"][name] = {"hits": value, "times": []}
            else:
                results["times"][name]["hits"] += value
    return results


def collect_data_and_write_to_file(
    comm: Optional[MPI.Comm],
    hits_per_step,
    times_per_step,
    experiment_name,
    time_step,
    backend,
    hash="",
) -> None:
    """
    collect the gathered data from all the ranks onto rank 0 and write the timing file
    """
    if comm:
        comm.Barrier()
        is_root = comm.Get_rank() == 0
    else:
        is_root = True

    results = None
    if is_root:
        print("Gathering Times")
        results = set_experiment_info(experiment_name, time_step, backend, hash)
        results = gather_hit_counts(hits_per_step, results)

    if comm:
        results = gather_timing_data(times_per_step, results, comm)
    else:
        results = put_data_into_dict(times_per_step, results)

    if is_root:
        write_global_timings(backend, bool(comm), results)
