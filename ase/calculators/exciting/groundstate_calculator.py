"""
ASE Calculator for the ground state exciting DFT code
"""
from typing import Union, List, Optional
from pathlib import Path

import ase
from ase.calculators.genericfileio import (GenericFileIOCalculator, CalculatorTemplate)
from ase.calculators.exciting.runner import ExcitingRunner, SubprocessRunResults
from ase.calculators.calculator import InputError

# TODO Move me
class ExcitingInput:
    """
    Base class for exciting inputs
    """

    # TODO(Alex) Strip all entries apart from attributes from dictionary
    def attributes_to_dict(self) -> dict:
        dictionary = self.__dict__
        return dictionary





# TODO. Implement me and move me
def query_exciting_version():
    return 'None'


class ExcitingProfile:
    """
    A profile defines all quantities that are configurable (variable)
    for a given machine or platform.

    Considered inheriting a runner but decided against it
    This is not used by
    """
    def __init__(self, exciting_root, species_path):
        self.species_path = species_path
        self.version = query_exciting_version(exciting_root)


class ExcitingGroundStateTemplate(CalculatorTemplate):
    """
    Template for Ground State Exciting Calculator,
    requiring implementations for the methods defined in CalculatorTemplate.
    """

    program_name = 'exciting'
    # TODO(Alex) Add parsers here i.e.
    # parser = {'info.xml': Callable[str, dict]}
    parser = {'info.xml': lambda file_name: {}}
    output_names = list(parser)
    implemented_properties = ['energy', 'forces']

    def __init__(self):
        """
        Initialise with constant class attributes.
        """
        super().__init__(self.program_name, self.implemented_properties)

    def write_input(self,
                    directory: Path,
                    atoms: ase.Atoms,
                    input_parameters: Union[dict, ExcitingInput],
                    properties: List[str]):
        """
        Write an exciting input.xml file

        :param Path directory: Directory in which to run calculator.
        :param ase.Atoms atoms: ASE atoms object.
        :param Union[dict, ExcitingInput] input_parameters: exciting groundstate input parameters
        :param List[str] properties: List of output properties.
        """
        #TODO Implement
        # directory.mkdir(exist_ok=True, parents=True)
        # Convert exciting inputs and ase.Atoms into an xml string
        # input_xml = 'Add functions to compose and return me'
        # Write the XML string to file
        # Do something or nothing with properties (maybe check against input?)
        return

    def execute(self, directory, exciting_calculation: ExcitingRunner) -> SubprocessRunResults:
        """
        Given an exciting calculation profile, execute the calculation.
        Method could be static, but maintaining API consistent with CalculatorTemplate

        :param directory: Directory in which to execute the calculator
        :param ExcitingRunner exciting_calculation: Generic `execute` expects a profile, however
         it is simply used to execute the program, therefore we just pass an ExcitingRunner.
        :return SubprocessRunResults: Results of subprocess.run
        """
        return exciting_calculation.run(directory)

    def read_results(self, directory: Path) -> dict:
        """
        Parse results from each ground state output file
        """
        results = {}
        for file_name in self.output_names:
            full_file_path = directory / file_name
            result: dict = self.parser[file_name](full_file_path)
            results.update(result)
        return results


def check_key_present(key, exciting_input: Union[ExcitingInput, dict]) -> bool:
    """
    Check species path is specified in the exciting_input
    """
    if isinstance(exciting_input, ExcitingInput):
        keys = ExcitingInput.__dict__
    else:
        keys = list(exciting_input)

    return key in keys


class ExcitingGroundStateResults:
    """
    Exciting Ground State Results
    """
    def __init__(self, results: dict) -> None:
        self.results = results
        self.completed = self.calculation_completed()
        self.converged = self.calculation_converged()

    def calculation_completed(self) -> bool:
        return False

    def calculation_converged(self) -> bool:
        return False


class ExcitingGroundState(GenericFileIOCalculator):
    """
    Exciting Ground StateCalculator Class.

    Base class implements the calculate method.

    Must supply to the constructor:
        * runner: ExcitingRunner: This should be a `profile` which is the machine-specific
          settings (run command, species paths, etc), however in exciting's case, this doesn't
          make sense. The species path is specified in the input file, and should therefore be
          an attribute of ExcitingInput. The only other machine-specific setting is the BinaryRunner.
          Furthermore, in GenericFileIOCalculator.calculate, profile is only used to provide a
          run method. We therefore pass the BinaryRunner in the place of a profile.

        * exciting_input ExcitingInput: exciting input parameters, including the species path
          BUT minus the structure, which is defined in ASE's Atoms object.

        * directory: Directory in which to run/execute the job.

    To the calculate method args:
        * atoms           ASE atoms object
        * properties      Output properties, as defined in a CalculatorTemplate
        * system_changes  ?

    via self:
        * directory      Directory in which to run/execute the job.
        * template       Specialised exciting template, containing write_input, execute and read_results methods
        * parameters     exciting_input. Can be defined as a class or Object. Responsibility
                         of the specialised write method.

    TODO(Alex) What methods do we need from our old calculator, and what exist in the base classes?
     Things to get results, based on properties

     TODO(Alex) We could support a specific set of keyword args, then use either a) Input dict/object
      or b) keywords
      List of keyword inputs from the old calculator:
        species_path, kpts, autormt, tshift
    """

    # Input options that must be present in the exciting_input
    required_inputs = ['species_path']

    def __init__(self, *,
                 runner: ExcitingRunner,
                 exciting_input: Union[ExcitingInput, dict],
                 directory='./'):

        self.runner = runner
        self.exciting_input = exciting_input
        self.directory = directory
        self.template = ExcitingGroundStateTemplate()

        for key in self.required_inputs:
            if not check_key_present(key, self.exciting_input):
                raise InputError(f'Key missing from exciting input: {key}')

        super().__init__(profile=runner,
                         template=self.template,
                         parameters=exciting_input,
                         directory=directory
                         )

    # TODO(Alex) Would rather remove properties from our calculate API
    def calculate(self,
                  atoms: ase.Atoms,
                  properties: Optional[List[str]] = None,
                  system_changes=None) -> ExcitingGroundStateResults:
        """
        Run an exciting calculation and capture the results in ExcitingGroundStateResults object.
        """
        if properties is None:
            properties = self.template.implemented_properties
        super().calculate(atoms, properties, system_changes)
        return ExcitingGroundStateResults(self.results)

