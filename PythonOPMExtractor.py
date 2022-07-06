#!/usr/bin/env python3

#
# PythonOPMExtractor.py
# Compatible with: Python 3.9
#

################################################################################
# License
################################################################################
# The MIT License (MIT)
#
# Copyright (C) 2022 Jan Szczuryk <jan.szczuryk@gmail.com>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
################################################################################   

import os
import sys
import base64
import xml.etree.ElementTree as ET
from enum import IntEnum
from collections import OrderedDict
from typing import Final

class OPMExtractor:

    class OPMExtractorError(Exception):
        """ Error specific to logic inside OPMExctactor class """
        pass

    class ExceptionMode(IntEnum):
        PRINT_STDERR = 1
        RAISE = 2
        PRINT_AND_RAISE = 3
    
    class MessageMode(IntEnum):
        PRINT_STDOUT = 1
        NO_PRINT = 2

    exception_mode: ExceptionMode = None
    message_mode: MessageMode = None
    indentation: str = "\t"
    input_file: str = None
    output_path: str = None
    loaded_package_root: ET.Element = None
    saved_package_files: list = None
    saved_package_sopm: str = None

    def __init__(self,
                input_file: str,
                output_path: str,
                exception_mode: ExceptionMode = ExceptionMode.PRINT_STDERR,
                message_mode: MessageMode = MessageMode.PRINT_STDOUT,
                indentation: str = "\t") -> None:
        self.input_file = input_file
        self.output_path = output_path
        self.exception_mode = exception_mode
        self.message_mode = message_mode
        self.indentation = indentation

    """ 
        Handlers:
    """
    def handle_exception(self, exception: BaseException) -> None:
        if self.exception_mode is self.ExceptionMode.PRINT_STDERR:
            self._handle_exception_print_stderr(exception)
        elif self.exception_mode is self.ExceptionMode.RAISE:
            self._handle_exception_raise(exception)
        elif self.exception_mode is self.ExceptionMode.PRINT_AND_RAISE:
            self._handle_exception_print_stderr(exception)
            self._handle_exception_raise(exception)

    def _handle_exception_print_stderr(self, exception: BaseException) -> None:
        print(f"{exception}", file=sys.stderr)

    def _handle_exception_raise(self, exception: BaseException) -> None:
        raise exception

    def handle_message(self, message: str) -> None:
        if self.message_mode is self.MessageMode.PRINT_STDOUT:
            self._handle_message_print_stdout(message)
        elif self.message_mode is self.MessageMode.NO_PRINT:
            pass

    def _handle_message_print_stdout(self, message: str) -> None:
        print(f"{message}", file=sys.stdout)

    """ 
        Public interface:
        - set_configuration()
        - load_input()
        - extract_package_files()
        - extract_package_sopm()
    """

    """ START set_configuration """
    def set_configuration(self, configuration: dict) -> None:
        configurable = [
            'exception_mode',
            'message_mode',
            'indentation'
        ]

        for name in configurable:
            if name not in configuration:
                continue
            if not isinstance(configuration[name], type(getattr(self, name))):
                continue
            
            setattr(self, name, configuration[name])
    """ END set_configuration """

    """ START load_input """
    def load_input(self) -> None:
        try:
            package_tree = ET.parse(self.input_file)
            self.loaded_package_root = package_tree.getroot()
        except FileNotFoundError:
            self.handle_exception(
                Exception(f"File '{self.input_file}' not found!")
            )
        except BaseException as err:
            raise err
        else:
            self.handle_message(f"File '{self.input_file}' loaded!")
    """ END load_input """

    """ START extract_package_files """
    def extract_package_files(self) -> None:
        try: 
            self.saved_package_files = list()
            
            tag_filelist = self.loaded_package_root.find('Filelist')

            for tag in tag_filelist:
                self._extract_from_file_tag(tag)               
                self.saved_package_files.append(tag.attrib)
                
        except self.OPMExtractorError as err:
            self.handle_exception(err)
        except BaseException as err:
            raise err
    
    def _extract_from_file_tag(self, file_tag: ET.Element) -> None:
        if file_tag.tag != 'File':
            raise self.OPMExtractorError(f"Tag is supposed to be named 'File'!")

        if file_tag.get('Permission', default=None) is None \
            or file_tag.get('Location', default=None) is None:
            raise self.OPMExtractorError(f"Tag 'File' is supposed to have 'Permission' and 'Location' attributes!")

        tag_encoding = file_tag.get('Encode', default=None)
        if tag_encoding != 'Base64':
            raise self.OPMExtractorError(f"Tag 'File' is has unsupported '{tag_encoding}' encoding!")

        tag_data = file_tag.text

        tag_location = file_tag.get('Location', default=None)
        if tag_location is None:
            raise self.OPMExtractorError(f"Tag 'File' has no 'Location' attribute!")

        tag_permission = file_tag.get('Permission', default=None) or '660'

        file_location = os.path.join(self.output_path, tag_location)
        file_data = self._decode_base64(tag_data)
        file_permission = int(tag_permission, base=8)

        self._write_binary_file(file_location, file_data)
        self._set_file_permissions(file_location, file_permission)

        self.handle_message(f"Saved file '{file_location}'")

    def _decode_base64(self, text) -> bytes:
        return base64.b64decode(text.replace('\n', ''))

    def _write_binary_file(self, path: str, file_data: bytes) -> None:
        os.makedirs(
            name=os.path.dirname(path),
            mode=0o755,
            exist_ok=True
        )

        with open(file=path, mode='wb') as f:
            f.write(file_data)
            f.close()

    def _set_file_permissions(self, path: str, permissions: int) -> None:
        os.chmod(path, permissions)
    """ END extract_package_files """

    """ START extract_package_sopm """
    def extract_package_sopm(self) -> None:
        try:
            tags_all = self._get_package_tag_names()
            
            package_xml_root = self._build_package_xml_root(tags_all)

            tag_name = self.loaded_package_root.find('./Name')
            if tag_name is None:
                raise self.OPMExtractorError(f"Tag 'Name' is supposed to exist!")

            sopm_file_location = os.path.join(self.output_path, f"{tag_name.text}.sopm")

            self._write_xml_root(sopm_file_location, package_xml_root)
            self._set_file_permissions(sopm_file_location, 0o644)

        except self.OPMExtractorError as err:
            self.handle_exception(err)
        except BaseException as err:
            raise err
        else:
            self.handle_message(f"Saved file '{sopm_file_location}'!")

    def _get_package_tag_names(self) -> list:
        tags_all = [ tag.tag for tag in self.loaded_package_root.findall('./') ]

        # Get rid of duplicates
        tags_all = list(OrderedDict.fromkeys(tags_all))

        tags_to_exclude = [
            'BuildCommitID',
            'BuildDate',
            'BuildHost',
        ]
        for tag in tags_to_exclude:
            if tag in tags_all:
                tags_all.remove(tag)

        return tags_all

    def _build_package_xml_root(self, all_tags: list) -> ET.ElementTree:
        tree_builder = ET.TreeBuilder()
        tree_builder.start('otrs_package', {'version': "1.1"})

        for tag_name in all_tags:
            for tag in self.loaded_package_root.iter(tag_name):
                self._add_xml_tag(tree_builder, tag, None)

        tree_builder.end('otrs_package')

        xml_root = tree_builder.close()

        # Replace Filelist tag
        tag_filelist = xml_root.find('./Filelist')
        if tag_filelist is not None:
            tag_filelist.clear()

            for tag_attrib in self.saved_package_files:
                new_attrib = tag_attrib
                del new_attrib['Encode']
                tag_filelist.append(ET.Element('File', attrib=new_attrib))

        return ET.ElementTree(xml_root)

    def _add_xml_tag(self, tree_builder: ET.TreeBuilder, tag: ET.Element,
            parent: ET.Element = None) -> None:
        new_tag = None

        if parent is None:    
            tree_builder.start(tag.tag, tag.attrib)
            tree_builder.data(tag.text)
            new_tag = tree_builder.end(tag.tag)
        else:
            new_tag = ET.SubElement(parent, tag.tag, tag.attrib)
            new_tag.text = tag.text

        subtags = list(tag.iterfind('./'))

        if subtags:
            for subtag in subtags:
                self._add_xml_tag(tree_builder, subtag, new_tag)

    def _write_xml_root(self, path: str, xml_root: ET.ElementTree) -> None:
        # Format XML with tabs
        ET.indent(xml_root, space=self.indentation, level=0)

        xml_root.write(path,
                        encoding='UTF-8', xml_declaration=True,
                        method='xml', short_empty_elements=True)
    """ END extract_package_sopm """

"""
    Wrapper for OPMExtractor class
"""

class Program:
    """ Constants """
    NAME: Final[str] = 'PythonOPMExtractor'
    VERSION: Final[str] = 'v1.1.0-pre1'

    """ Config Variables """
    config = {
        'exception_mode': OPMExtractor.ExceptionMode.PRINT_STDERR,
        'message_mode': OPMExtractor.MessageMode.PRINT_STDOUT,
        'indentation': "\t",
    }

    arguments: list = list()
    input_file: str = ''
    output_path: str = ''
    is_quiet: bool = False

    def __init__(self, arguments) -> None:
        self.arguments = arguments

    """ Entrypoint for the program """
    def main(self) -> None:

        self.handleArguments(self.arguments)

        if not self.is_quiet:
            print(f".:: {self.NAME} {self.VERSION} ::.")

        extractor = OPMExtractor(self.input_file, self.output_path)

        if self.is_quiet:
            self.config['message_mode'] = OPMExtractor.MessageMode.NO_PRINT

        extractor.set_configuration(self.config)

        extractor.load_input()
        extractor.extract_package_files()
        extractor.extract_package_sopm()
        
        if not self.is_quiet:
            print(f"Done!")

    def handleArguments(self, arguments: list) -> None:
        arguments_count = len(arguments)

        if arguments_count >= 2:
            self._handleArguments2(arguments)

        handle_arguments = {
            3: self._handleArguments3,
            4: self._handleArguments4,
        }        

        handler = handle_arguments[arguments_count]
        if handler:
            handler(arguments)
        else:
            self.printUsage()
            exit(0)
        
    def _handleArguments2(self, arguments: list):
        if (arguments[1] == '-h' or arguments[1] == '--help'):
            self.printUsage()
            exit(0)
        if (arguments[1] == '-v' or arguments[1] == '--version'):
            self.printVersion()
            exit(0)

    def _handleArguments3(self, arguments: list):
        self.input_file = str(arguments[1])
        self.output_path = str(arguments[2])

    def _handleArguments4(self, arguments: list):
        if (arguments[1] == '-q' or arguments[1] == '--quiet'):
            self.input_file = str(arguments[2])
            self.output_path = str(arguments[3])
            self.is_quiet = True

    def printUsage(self) -> None:
        usage = f"""Usage: {self.arguments[0]} [options] <opm file> <output directory>

    Options:
        -h, --help              shows this help message and exit
        -v, --version           shows program version and exit
        -q, --quiet             runs program in quiet mode and suppresses messages"""
        print(usage)

    def printVersion(self) -> None:
        print(f"{self.NAME} {self.VERSION}")

if __name__ == '__main__':
    program = Program(sys.argv)
    program.main()
