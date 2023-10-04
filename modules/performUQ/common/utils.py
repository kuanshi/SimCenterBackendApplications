import glob
import os
import shutil
import subprocess
import sys
import os
import numpy as np
from typing import Union, Optional, Any
from numpy.typing import NDArray
import traceback
from multiprocessing.pool import Pool
from ERAClasses.ERADist import ERADist
from ERAClasses.ERANataf import ERANataf
import quoFEM_RV_models 


def _copytree(src, dst, symlinks=False, ignore=None):
    if not os.path.exists(dst):
        os.makedirs(dst)
    for item in os.listdir(src):
        s = os.path.join(src, item)
        d = os.path.join(dst, item)
        if os.path.isdir(s):
            _copytree(s, d, symlinks, ignore)
        else:
            try:
                if not os.path.exists(d) or \
                    os.stat(s).st_mtime - os.stat(d).st_mtime > 1:
                        shutil.copy2(s, d)
            except Exception as ex:
                msg = f"Could not copy {s}. \
                    The following error occurred: \n{ex}"
                return msg
    return "0"


def _append_msg_in_out_file(msg, out_file_name: str = "ops.out"):
    if glob.glob(out_file_name):
        with open(out_file_name, "r") as text_file:
            error_FEM = text_file.read()

        startingCharId = error_FEM.lower().find("error")

        if startingCharId >0:
            startingCharId = max(0,startingCharId-20)
            endingID = max(len(error_FEM),startingCharId+200)
            errmsg = error_FEM[startingCharId:endingID]
            errmsg=errmsg.split(" ", 1)[1]
            errmsg=errmsg[0:errmsg.rfind(" ")]
            msg += "\n"
            msg += "your model says...\n"
            msg += "........\n" + errmsg + "\n........ \n"
            msg += "to read more, see " + os.path.join(os.getcwd(), 
                                                       out_file_name)
    
    return msg


class ModelEvaluationError(Exception):
    def __init__(self, msg: str) -> None:
        super().__init__(msg)


class SimCenterWorkflowDriver:
    def __init__(self, num_rv: int, full_path_of_tmpSimCenter_dir: str, 
                 list_of_dir_names_to_copy_files_from: list[str], 
                 list_of_rv_names: list[str], driver_filename: str, 
                 length_of_results: int,
                 workdir_prefix: str = "workdir",
                 ignore_nans: bool = True) -> None:
        
        self.num_rv = num_rv
        self.full_path_of_tmpSimCenter_dir = full_path_of_tmpSimCenter_dir
        self.list_of_dir_names_to_copy_files_from = \
            list_of_dir_names_to_copy_files_from
        self.list_of_rv_names = list_of_rv_names
        self.driver_filename = driver_filename
        self.length_of_results = length_of_results
        self.workdir_prefix = workdir_prefix
        self.ignore_nans = ignore_nans

        if self.num_rv != len(self.list_of_rv_names):
            raise ModelEvaluationError(f"Error during model specification: \
                    Inconsistency between number of rvs ({num_rv = }) and \
                    length of list of rv names ({len(list_of_rv_names) = })")
    
    def _check_size_of_sample(self, sample_values: NDArray) -> None:
        num_samples = len(sample_values)
        if num_samples > 1:
            msg = f"Do one simulation at a time. There were {num_samples} \
                samples provided in the sample value {sample_values}."
            raise ModelEvaluationError(msg)
        
        for i in range(num_samples):
            num_values_in_each_sample = len(sample_values[i])
            if num_values_in_each_sample != self.num_rv:
                msg = f"Expected {self.num_rv} values in each sample, found \
                    {num_values_in_each_sample} in {sample_values}."
                raise ModelEvaluationError(msg)        
    
    def _create_workdir(self, simulation_number: int) -> str:
        workdir = os.path.join(
            self.full_path_of_tmpSimCenter_dir, 
            f"{self.workdir_prefix}.{simulation_number + 1}")
        if os.path.exists(workdir):
            for root, dirs, files in os.walk(workdir):
                for file in files:
                    try:
                        os.unlink(os.path.join(root, file))
                    except:
                        msg = f"Could not remove file {file} from {workdir}."
                        raise ModelEvaluationError(msg)
                for dir in dirs:
                    try:
                        shutil.rmtree(os.path.join(root, dir))
                    except:
                        msg = f"Could not remove directory {dir} \
                            from {workdir}."
                        raise ModelEvaluationError(msg)

        for src_dir in self.list_of_dir_names_to_copy_files_from:
            src = os.path.join(self.full_path_of_tmpSimCenter_dir, src_dir)
            msg = _copytree(src, workdir)
            if msg != "0":
                raise ModelEvaluationError(msg)
        return workdir
    
    def _create_params_file(self, sample_values: NDArray, 
                            workdir: str) -> None:
        list_of_strings_to_write = []
        list_of_strings_to_write.append(f"{self.num_rv}")
        for i, rv in enumerate(self.list_of_rv_names):
            list_of_strings_to_write.append(f"{rv} {sample_values[0][i]}")
        try: 
            with open(os.path.join(workdir, "params.in"), "w") as f:
                f.write("\n".join(list_of_strings_to_write))
        except Exception as ex:
            raise ModelEvaluationError(f"Failed to create params.in file in \
                        {workdir}. The following error occurred: \n{ex}")

    def _execute_driver_file(self, workdir: str) -> None:
        command = f"{os.path.join(workdir, self.driver_filename)} \
                     1> model_eval.log 2>&1"
        os.chdir(workdir)
        completed_process = subprocess.run(command, shell=True)
        try:
            completed_process.check_returncode()
        except subprocess.CalledProcessError as ex:
            returnStringList = ["Failed to run the model."]
            returnStringList.append(f"The command to run the model was \
                                    {ex.cmd}")
            returnStringList.append(f"The return code was {ex.returncode}")
            returnStringList.append(f"The following error occurred: \n{ex}")
            raise ModelEvaluationError(f"\n\n".join(returnStringList))
    
    def _read_outputs_from_results_file(self, workdir: str) -> NDArray:
        if glob.glob("results.out"):
            outputs = np.loadtxt("results.out").flatten()
        else:
            msg = f"Error running FEM: 'results.out' missing at {workdir}\n"
            msg = _append_msg_in_out_file(msg, out_file_name="ops.out")
            raise ModelEvaluationError(msg)

        if outputs.shape[0] == 0:
            msg = "Error running FEM: 'results.out' is empty\n"
            msg = _append_msg_in_out_file(msg, out_file_name="ops.out")
            raise ModelEvaluationError(msg)
        
        if outputs.shape[0] != self.length_of_results:
            msg = f"Error running FEM: 'results.out' contains \
                {outputs.shape[0]} values, expected to get \
                {self.length_of_results} values\n"
            msg = _append_msg_in_out_file(msg, out_file_name="ops.out")
            raise ModelEvaluationError(msg)

        if not self.ignore_nans:
            if np.isnan(np.sum(outputs)):
                msg = f"Error running FEM: Response value in {workdir} is NaN"
                raise ModelEvaluationError(msg)

        return outputs

    def evaluate_model_once(self, simulation_number: int, \
                            sample_values: NDArray) -> Union[str, NDArray]:
        outputs = ""
        try:
            sample_values = np.atleast_2d(sample_values)
            self._check_size_of_sample(sample_values)
            workdir = self._create_workdir(simulation_number)
            self._create_params_file(sample_values, workdir)
            self._execute_driver_file(workdir)
            outputs = self._read_outputs_from_results_file(workdir)
        except Exception:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            outputs = f"\nSimulation number: {simulation_number}\n" \
                      + f"Samples values: {sample_values}\n" 
            outputs += "".join(traceback.format_exception(exc_type, 
                                                          exc_value, 
                                                          exc_traceback))
        finally:
            os.chdir(self.full_path_of_tmpSimCenter_dir)
        return outputs


class ParallelRunnerMultiprocessing:
    def __init__(self, run_type: str = "runningLocal") -> None:
        self.run_type = run_type
        self.num_processors = self.get_num_processors()
    
    def get_num_processors(self) -> int:
        num_processors = os.cpu_count()
        if num_processors is None:
            num_processors = 1
        if num_processors < 1:
            raise ValueError(f"Number of processes must be at least 1. \
                             Got {num_processors}")
        return num_processors

    def get_pool(self) -> Pool:
        self.pool = Pool(processes=self.num_processors)
        return self.pool
    
    def close_pool(self) -> None:
        self.pool.close()

    def run(self, func, iterable, chunksize: Optional[int] = None) -> list:
        try:
            isinstance(self.pool, Pool)
        except AttributeError:
            self.pool = self.get_pool()   
        return self.pool.starmap(func=func, iterable=iterable, 
                                 chunksize=chunksize)


# def get_parallel_runner_instance(run_type: str):
#     if run_type == "runningRemote":
#         return ParallelRunnerMPI4PY(run_type)
#     else:
#         return ParallelRunnerMultiprocessing(run_type)


# def get_parallel_runner_function(parallel_runner: 
#                                  Union[ParallelRunnerMultiprocessing, 
#                                        ParallelRunnerMPI4PY]):
#     return parallel_runner.run

def make_ERADist_object(name, opt, val) -> ERADist:
    return ERADist(name=name, opt=opt, val=val)


def create_one_marginal_distribution(rv_data) -> ERADist:
    string = f'quoFEM_RV_models.{rv_data["distribution"]}'\
            + f'{rv_data["inputType"]}.model_validate({rv_data})'
    rv = eval(string)
    return make_ERADist_object(name=rv.ERAName, opt=rv.ERAOpt, val=rv.ERAVal)


def make_list_of_marginal_distributions(
        list_of_random_variables_data) -> list[ERADist]:
    marginal_ERAdistribution_objects_list = []
    for rv_data in list_of_random_variables_data:
        marginal_ERAdistribution_objects_list.append(
            create_one_marginal_distribution(rv_data))
    return marginal_ERAdistribution_objects_list


def make_correlation_matrix(correlation_matrix_data, num_rvs) -> NDArray:
    return np.atleast_2d(correlation_matrix_data).reshape((num_rvs, num_rvs))


def make_ERANataf_object(list_of_ERADist, correlation_matrix) -> ERANataf:
    return ERANataf(M=list_of_ERADist, Correlation=correlation_matrix)


class ERANatafJointDistribution:
    def __init__(self, list_of_random_variables_data: list, 
                 correlation_matrix_data: NDArray) -> None:
        self.list_of_random_variables_data = list_of_random_variables_data
        self.correlation_matrix_data = correlation_matrix_data

        self.num_rvs = len(self.list_of_random_variables_data)
        self.correlation_matrix = make_correlation_matrix(
            self.correlation_matrix_data, self.num_rvs)
        self.marginal_ERAdistribution_objects_list = \
            make_list_of_marginal_distributions(
                self.list_of_random_variables_data)
        self.ERANataf_object = make_ERANataf_object(
            self.marginal_ERAdistribution_objects_list, 
            self.correlation_matrix)

    def u_to_x(self, u: NDArray, 
               jacobian: bool=False) -> Union[tuple[NDArray[np.float64], Any], 
                                              NDArray[np.float64]]:
        return self.ERANataf_object.U2X(U=u, Jacobian=jacobian) 
    
    def x_to_u(self, x: NDArray, 
               jacobian: bool=False) -> Union[tuple[NDArray[np.floating[Any]], 
                                                    NDArray[np.floating[Any]]], 
                                                    NDArray[np.floating[Any]]]:
        return self.ERANataf_object.X2U(X=x, Jacobian=jacobian)

    def pdf(self, x: NDArray) -> Union[Any, NDArray[np.float64]]:
        return self.ERANataf_object.pdf(X=x)
    
    def logpdf(self, x: NDArray) -> NDArray[np.float64]:
        return np.log(self.pdf(x))
    
    def cdf(self, x: NDArray) -> float:
        return self.ERANataf_object.cdf(X=x)
    
    def random(self, list_of_rngs: list[np.random.Generator]=[], 
               n: int=1) -> Union[tuple[NDArray[np.float64], Any], 
                                  NDArray[np.float64]]:
        if list_of_rngs == []:
            list_of_rngs = [np.random.default_rng(seed=i) for i in range(len(
                self.marginal_ERAdistribution_objects_list))]
        u = np.zeros((n, len(list_of_rngs)))
        for i, rng in enumerate(list_of_rngs):
            u[:, i] = rng.normal(size=n)
        return self.u_to_x(u)
