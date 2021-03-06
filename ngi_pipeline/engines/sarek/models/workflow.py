import os
from string import Template

from ngi_pipeline.engines.sarek.exceptions import ParserException
from ngi_pipeline.engines.sarek.parsers import QualiMapParser, PicardMarkDuplicatesParser


class SarekWorkflowStep(object):
    """
    The SarekWorkflowStep class represents an analysis step in the Sarek workflow. Primarily, it provides a method for
    creating the step-specific command line.
    """

    available_tools = []

    def __init__(
            self,
            path_to_nextflow,
            path_to_sarek,
            **sarek_args):
        """
        Create a SarekWorkflowStep instance according to the passed parameters.

        :param path_to_nextflow: path to the nextflow executable
        :param path_to_sarek: path to the main Sarek folder
        :param sarek_args: additional Sarek parameters to be included on the command line
        """
        self.nf_path = path_to_nextflow
        self.sarek_path = path_to_sarek
        # create a dict with parameters based on the passed key=value arguments
        self.sarek_args = {k: v for k, v in sarek_args.items() if k not in ["nf_path", "sarek_path"]}
        # add/filter a tools parameter against the valid tools for the workflow step
        self.sarek_args["tools"] = self.valid_tools(self.sarek_args.get("tools", []))
        # expand any parameters passed as list items into a ","-separated string
        self.sarek_args = {k: v if type(v) is not list else ",".join(v) for k, v in self.sarek_args.items()}

    def _append_argument(self, base_string, name, hyphen="--"):
        """
        Append an argument with a placeholder for the value to the supplied string in a format suitable for the
        string.Template constructor. If no value exists for the argument name among this workflow step's config
        parameters, the supplied string is returned untouched.

        Example: step._append_argument("echo", "hello", "") should return "echo hello ${hello}", provided the step
        instance has a "hello" key in the step.sarek_args dict.

        :param base_string: the string to append an argument to
        :param name: the argument name to add a placeholder for
        :param hyphen: the hyphen style to prefix the argument name with (default "--")
        :return: the supplied string with an appended argument name and placeholder
        """
        # NOTE: a numeric value of 0 will be excluded (as will a boolean value of False)!
        if not self.sarek_args.get(name):
            return base_string
        return "{0} {2}{1} ${{{1}}}".format(base_string, name, hyphen)

    def command_line(self):
        """
        Generate the command line for launching this analysis workflow step. The command line will be built using the
        Sarek arguments passed to the step's constructor and returned as a string.

        :return: the command line for the workflow step as a string
        """
        single_hyphen_args = ["config", "profile"]
        template_string = "${nf_path} run ${sarek_step_path}"
        for argument_name in single_hyphen_args:
            template_string = self._append_argument(template_string, argument_name, hyphen="-")
        for argument_name in filter(lambda n: n not in single_hyphen_args, self.sarek_args.keys()):
            template_string = self._append_argument(template_string, argument_name, hyphen="--")
        command_line = Template(template_string).substitute(
            nf_path=self.nf_path,
            sarek_step_path=os.path.join(self.sarek_path, self.sarek_step()),
            **self.sarek_args)
        return command_line

    def sarek_step(self):
        raise NotImplementedError("The Sarek workflow step definition for {} has not been defined".format(type(self)))

    def valid_tools(self, tools):
        """
        Filter a list of tools against the list of available tools for the analysis step.

        :param tools: a list of tool names
        :return: a list of tool names valid for this workflow step
        """
        return list(filter(lambda t: t in self.available_tools, tools))

    @classmethod
    def report_files(cls, analysis_sample):
        return []


class SarekPreprocessingStep(SarekWorkflowStep):

    def sarek_step(self):
        return "main.nf"

    @classmethod
    def report_files(cls, analysis_sample):
        """
        Get a list of the report files resulting from this processing step and the associated parsers.

        :param analysis_sample: the SarekAnalysisSample that was analyzed
        :return: a list of tuples where the first element is a parser class instance and the second is the path to the
        result file that the parser instance should parse
        """
        report_dir = os.path.join(analysis_sample.sample_analysis_path(), "Reports")
        # MarkDuplicates output files may be named differently depending on if the pipeline was started with a single
        # fastq file pair or multiple file pairs
        markdups_dir = os.path.join(report_dir, "MarkDuplicates")
        metric_files = filter(lambda f: f.endswith(".metrics"), os.listdir(markdups_dir))
        if not metric_files:
            raise ParserException(cls, "no metrics file for MarkDuplicates found for sample {} in {}".format(
                analysis_sample.sampleid, markdups_dir))
        markdups_metrics_file = metric_files.pop()
        if metric_files:
            raise ParserException(cls, "multiple metrics files for MarkDuplicates found for sample {} in {}".format(
                analysis_sample.sampleid, markdups_dir))
        return [
            [
                QualiMapParser,
                os.path.join(report_dir, "bamQC", analysis_sample.sampleid, "genome_results.txt")],
            [
                PicardMarkDuplicatesParser,
                os.path.join(markdups_dir, markdups_metrics_file)]]


class SarekGermlineVCStep(SarekWorkflowStep):

    available_tools = [
        "haplotypecaller",
        "strelka",
        "manta"
    ]

    def sarek_step(self):
        return "germlineVC.nf"


class SarekAnnotateStep(SarekWorkflowStep):

    available_tools = [
        "snpeff",
        "vep"
    ]

    def sarek_step(self):
        return "annotate.nf"


class SarekMultiQCStep(SarekWorkflowStep):

    def sarek_step(self):
        return "runMultiQC.nf"

