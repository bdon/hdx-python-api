# -*- coding: utf-8 -*-
"""Dataset class containing all logic for creating, checking, and updating datasets and associated resources.
"""
import logging
import sys
from datetime import datetime
from os.path import join
from typing import List, Union

from dateutil import parser
from six.moves import range

import hdx.data.organization
import hdx.data.showcase
from hdx.data.hdxobject import HDXObject, HDXError
from hdx.data.resource import Resource
from hdx.data.user import User
from hdx.utilities import raisefrom
from hdx.utilities.dictandlist import merge_two_dictionaries

logger = logging.getLogger(__name__)

max_attempts = 5
page_size = 1000
max_int = sys.maxsize

class Dataset(HDXObject):
    """Dataset class enabling operations on datasets and associated resources.

    Args:
        initial_data (Optional[dict]): Initial dataset metadata dictionary. Defaults to None.
        configuration (Optional[Configuration]): HDX configuration. Defaults to global configuration.
    """

    update_frequencies = {
        '0': 'Never',
        '1': 'Every day',
        '7': 'Every week',
        '14': 'Every two weeks',
        '30': 'Every month',
        '90': 'Every three months',
        '180': 'Every six months',
        '365': 'Every year',
        'never': '0',
        'every day': '1',
        'every week': '7',
        'every two weeks': '14',
        'every month': '30',
        'every three months': '90',
        'every six months': '180',
        'every year': '365',
        'daily': '1',
        'weekly': '7',
        'fortnightly': '14',
        'every other week': '14',
        'monthly': '30',
        'quarterly': '90',
        'semiannually': '180',
        'semiyearly': '180',
        'annually': '365',
        'yearly': '365'
    }

    def __init__(self, initial_data=None, configuration=None):
        # type: (Optional[dict], Optional[bool], Optional[Configuration]) -> None
        if not initial_data:
            initial_data = dict()
        super(Dataset, self).__init__(dict(), configuration=configuration)
        self.init_resources()
        # workaround: python2 IterableUserDict does not call __setitem__ in __init__,
        # while python3 collections.UserDict does
        for key in initial_data:
            self[key] = initial_data[key]

    @staticmethod
    def actions():
        # type: () -> dict
        """Dictionary of actions that can be performed on object

        Returns:
            dict: Dictionary of actions that can be performed on object
        """
        return {
            'show': 'package_show',
            'update': 'package_update',
            'create': 'package_create',
            'delete': 'package_delete',
            'search': 'package_search',
            'list': 'package_list',
            'all': 'current_package_list_with_resources'
        }

    def __setitem__(self, key, value):
        # type: (Any, Any) -> None
        """Set dictionary items but do not allow setting of resources

        Args:
            key (Any): Key in dictionary
            value (Any): Value to put in dictionary

        Returns:
            None
        """
        if key == 'resources':
            self.add_update_resources(value)
            return
        super(Dataset, self).__setitem__(key, value)

    def separate_resources(self):
        # type: () -> None
        """Move contents of resources key in internal dictionary into self.resources

        Returns:
            None
        """
        self._separate_hdxobjects(self.resources, 'resources', 'name', Resource)

    def init_resources(self):
        # type: () -> None
        """Initialise self.resources list

        Returns:
            None
        """
        self.resources = list()
        """:type : List[Resource]"""

    def add_update_resource(self, resource):
        # type: (Union[Resource,dict,str]) -> None
        """Add new or update existing resource in dataset with new metadata

        Args:
            resource (Union[Resource,dict,str]): Either resource id or resource metadata from a Resource object or a dictionary

        Returns:
            None
        """
        if isinstance(resource, str):
            resource = Resource.read_from_hdx(resource, configuration=self.configuration)
        elif isinstance(resource, dict):
            resource = Resource(resource, configuration=self.configuration)
        if isinstance(resource, Resource):
            if 'package_id' in resource:
                raise HDXError("Resource %s being added already has a dataset id!" % (resource['name']))
            resource_updated = self._addupdate_hdxobject(self.resources, 'name', resource)
            resource_updated.set_file_to_upload(resource.get_file_to_upload())
            return
        raise HDXError("Type %s cannot be added as a resource!" % type(resource).__name__)

    def add_update_resources(self, resources):
        # type: (List[Union[Resource,dict,str]]) -> None
        """Add new or update existing resources with new metadata to the dataset

        Args:
            resources (List[Union[Resource,dict,str]]): A list of either resource ids or resources metadata from either Resource objects or dictionaries

        Returns:
            None
        """
        if not isinstance(resources, list):
            raise HDXError('Resources should be a list!')
        for resource in resources:
            self.add_update_resource(resource)

    def delete_resource(self, resource):
        # type: (Union[Resource,dict,str]) -> bool
        """Delete a resource from the dataset

        Args:
            resource (Union[Resource,dict,str]): Either resource id or resource metadata from a Resource object or a dictionary

        Returns:
            bool: True if resource removed or False if not
        """
        return self._remove_hdxobject(self.resources, resource, delete=True)

    def get_resources(self):
        # type: () -> List[Resource]
        """Get dataset's resources

        Returns:
            List[Resource]: List of Resource objects
        """
        return self.resources

    def update_from_yaml(self, path=join('config', 'hdx_dataset_static.yml')):
        # type: (Optional[str]) -> None
        """Update dataset metadata with static metadata from YAML file

        Args:
            path (Optional[str]): Path to YAML dataset metadata. Defaults to config/hdx_dataset_static.yml.

        Returns:
            None
        """
        super(Dataset, self).update_from_yaml(path)
        self.separate_resources()

    def update_from_json(self, path=join('config', 'hdx_dataset_static.json')):
        # type: (Optional[str]) -> None
        """Update dataset metadata with static metadata from JSON file

        Args:
            path (Optional[str]): Path to JSON dataset metadata. Defaults to config/hdx_dataset_static.json.

        Returns:
            None
        """
        super(Dataset, self).update_from_json(path)
        self.separate_resources()

    @staticmethod
    def read_from_hdx(identifier, configuration=None):
        # type: (str, Optional[Configuration]) -> Optional['Dataset']
        """Reads the dataset given by identifier from HDX and returns Dataset object

        Args:
            identifier (str): Identifier of dataset
            configuration (Optional[Configuration]): HDX configuration. Defaults to global configuration.

        Returns:
            Optional[Dataset]: Dataset object if successful read, None if not
        """

        dataset = Dataset(configuration=configuration)
        result = dataset._dataset_load_from_hdx(identifier)
        if result:
            return dataset
        return None

    def _dataset_create_resources(self):
        # type: () -> None
        """Creates resource objects in dataset
        """

        if 'resources' in self.data:
            self.old_data['resources'] = self._copy_hdxobjects(self.resources, Resource, 'file_to_upload')
            self.init_resources()
            self.separate_resources()

    def _dataset_load_from_hdx(self, id_or_name):
        # type: (str) -> bool
        """Loads the dataset given by either id or name from HDX

        Args:
            id_or_name (str): Either id or name of dataset

        Returns:
            bool: True if loaded, False if not
        """

        if not self._load_from_hdx('dataset', id_or_name):
            return False
        self._dataset_create_resources()
        return True

    def check_required_fields(self, ignore_fields=list()):
        # type: (List[str]) -> None
        """Check that metadata for dataset and its resources is complete. The parameter ignore_fields
        should be set if required to any fields that should be ignored for the particular operation.

        Args:
            ignore_fields (List[str]): Fields to ignore. Default is [].

        Returns:
            None
        """
        self._check_required_fields('dataset', ignore_fields)

        for resource in self.resources:
            ignore_fields = ['package_id']
            resource.check_required_fields(ignore_fields=ignore_fields)

    def _dataset_merge_hdx_update(self, update_resources):
        # type: (bool) -> None
        """Helper method to check if dataset or its resources exist and update them

        Args:
            update_resources (bool): Whether to update resources

        Returns:
            None
        """
        merge_two_dictionaries(self.data, self.old_data)
        if 'resources' in self.data:
            del self.data['resources']
        old_resources = self.old_data.get('resources', None)
        filestore_resources = list()
        if update_resources and old_resources:
            ignore_fields = ['package_id']
            resource_names = set()
            for resource in self.resources:
                resource_name = resource['name']
                resource_names.add(resource_name)
                for old_resource in old_resources:
                    if resource_name == old_resource['name']:
                        logger.warning('Resource exists. Updating %s' % resource_name)
                        merge_two_dictionaries(resource, old_resource)
                        if old_resource.get_file_to_upload():
                            resource.set_file_to_upload(old_resource.get_file_to_upload())
                            filestore_resources.append(resource)
                        resource.check_required_fields(ignore_fields=ignore_fields)
                        break
            for old_resource in old_resources:
                if not old_resource['name'] in resource_names:
                    old_resource.check_required_fields(ignore_fields=ignore_fields)
                    self.resources.append(old_resource)
                    if old_resource.get_file_to_upload():
                        filestore_resources.append(old_resource)
        if self.resources:
            self.data['resources'] = self._convert_hdxobjects(self.resources)
        self._save_to_hdx('update', 'id')

        for resource in filestore_resources:
            for created_resource in self.data['resources']:
                if resource['name'] == created_resource['name']:
                    merge_two_dictionaries(resource.data, created_resource)
                    resource.update_in_hdx()
                    merge_two_dictionaries(created_resource, resource.data)
                    break

    def update_in_hdx(self, update_resources=True):
        # type: (Optional[bool]) -> None
        """Check if dataset exists in HDX and if so, update it

        Args:
            update_resources (Optional[bool]): Whether to update resources. Defaults to True.

        Returns:
            None
        """
        loaded = False
        if 'id' in self.data:
            self._check_existing_object('dataset', 'id')
            if self._dataset_load_from_hdx(self.data['id']):
                loaded = True
            else:
                logger.warning('Failed to load dataset with id %s' % self.data['id'])
        if not loaded:
            self._check_existing_object('dataset', 'name')
            if not self._dataset_load_from_hdx(self.data['name']):
                raise HDXError('No existing dataset to update!')
        self._dataset_merge_hdx_update(update_resources)

    def create_in_hdx(self):
        # type: () -> None
        """Check if dataset exists in HDX and if so, update it, otherwise create it

        Returns:
            None
        """
        self.check_required_fields()
        loadedid = None
        if 'id' in self.data:
            if self._dataset_load_from_hdx(self.data['id']):
                loadedid = self.data['id']
            else:
                logger.warning('Failed to load dataset with id %s' % self.data['id'])
        if not loadedid:
            if self._dataset_load_from_hdx(self.data['name']):
                loadedid = self.data['name']
        if loadedid:
            logger.warning('Dataset exists. Updating %s' % loadedid)
            self._dataset_merge_hdx_update(True)
            return

        filestore_resources = list()
        if self.resources:
            ignore_fields = ['package_id']
            for resource in self.resources:
                resource.check_required_fields(ignore_fields=ignore_fields)
                if resource.get_file_to_upload():
                    filestore_resources.append(resource)
            self.data['resources'] = self._convert_hdxobjects(self.resources)
        self._save_to_hdx('create', 'name')
        for resource in filestore_resources:
            for created_resource in self.data['resources']:
                if resource['name'] == created_resource['name']:
                    merge_two_dictionaries(resource.data, created_resource)
                    resource.update_in_hdx()
                    merge_two_dictionaries(created_resource, resource.data)
                    break
        self.init_resources()
        self.separate_resources()

    def delete_from_hdx(self):
        # type: () -> None
        """Deletes a dataset from HDX.

        Returns:
            None
        """
        self._delete_from_hdx('dataset', 'id')

    @staticmethod
    def search_in_hdx(query='*:*', configuration=None, **kwargs):
        # type: (Optional[str], Optional[Configuration], ...) -> List['Dataset']
        """Searches for datasets in HDX

        Args:
            query (Optional[str]): Query (in Solr format). Defaults to '*:*'.
            configuration (Optional[Configuration]): HDX configuration. Defaults to global configuration.
            **kwargs: See below
            fq (string): Any filter queries to apply
            sort (string): Sorting of the search results. Defaults to 'relevance asc, metadata_modified desc'.
            rows (int): Number of matching rows to return. Defaults to all datasets (sys.maxsize).
            start (int): Offset in the complete result for where the set of returned datasets should begin
            facet (string): Whether to enable faceted results. Default to True.
            facet.mincount (int): Minimum counts for facet fields should be included in the results
            facet.limit (int): Maximum number of values the facet fields return (- = unlimited). Defaults to 50.
            facet.field (List[str]): Fields to facet upon. Default is empty.
            use_default_schema (bool): Use default package schema instead of custom schema. Defaults to False.

        Returns:
            List[Dataset]: List of datasets resulting from query
        """

        dataset = Dataset(configuration=configuration)
        total_rows = kwargs.get('rows', max_int)
        start = kwargs.get('start', 0)
        all_datasets = None
        attempts = 0
        while attempts < max_attempts and all_datasets is None:  # if the count values vary for multiple calls, then must redo query
            all_datasets = list()
            counts = set()
            for page in range(total_rows // page_size + 1):
                pagetimespagesize = page * page_size
                kwargs['start'] = start + pagetimespagesize
                rows_left = total_rows - pagetimespagesize
                rows = min(rows_left, page_size)
                kwargs['rows'] = rows
                _, result = dataset._read_from_hdx('dataset', query, 'q', Dataset.actions()['search'], **kwargs)
                datasets = list()
                if result:
                    count = result.get('count', None)
                    if count:
                        counts.add(count)
                        no_results = len(result['results'])
                        for datasetdict in result['results']:
                            dataset = Dataset(configuration=configuration)
                            dataset.old_data = dict()
                            dataset.data = datasetdict
                            dataset._dataset_create_resources()
                            datasets.append(dataset)
                        all_datasets += datasets
                        if no_results < rows:
                            break
                    else:
                        break
                else:
                    logger.debug(result)
            if all_datasets and len(counts) != 1:  # Make sure counts are all same for multiple calls to HDX
                all_datasets = None
                attempts += 1
            else:
                ids = [dataset['id'] for dataset in all_datasets]  # check for duplicates (shouldn't happen)
                if len(ids) != len(set(ids)):
                    all_datasets = None
                    attempts += 1
        if attempts == max_attempts and all_datasets is None:
            raise HDXError('Maximum attempts reached for searching for datasets!')
        return all_datasets

    @staticmethod
    def get_all_dataset_names(configuration=None, **kwargs):
        # type: (Optional[Configuration], ...) -> List[str]
        """Get all dataset names in HDX

        Args:
            configuration (Optional[Configuration]): HDX configuration. Defaults to global configuration.
            **kwargs: See below
            limit (int): Number of rows to return. Defaults to all dataset names.
            offset (int): Offset in the complete result for where the set of returned dataset names should begin

        Returns:
            List[str]: List of all dataset names in HDX
        """
        dataset = Dataset(configuration=configuration)
        dataset['id'] = 'all dataset names'  # only for error message if produced
        return dataset._write_to_hdx('list', kwargs, 'id')

    @staticmethod
    def get_all_datasets(configuration=None, **kwargs):
        # type: (Optional[Configuration], ...) -> List['Dataset']
        """Get all datasets in HDX

        Args:
            configuration (Optional[Configuration]): HDX configuration. Defaults to global configuration.
            **kwargs: See below
            limit (int): Number of rows to return. Defaults to all datasets (sys.maxsize).
            offset (int): Offset in the complete result for where the set of returned datasets should begin

        Returns:
            List[Dataset]: List of all datasets in HDX
        """

        dataset = Dataset(configuration=configuration)
        dataset['id'] = 'all datasets'  # only for error message if produced
        total_rows = kwargs.get('limit', max_int)
        start = kwargs.get('offset', 0)
        all_datasets = None
        attempts = 0
        while attempts < max_attempts and all_datasets is None:  # if the dataset names vary for multiple calls, then must redo query
            all_datasets = list()
            for page in range(total_rows // page_size + 1):
                pagetimespagesize = page * page_size
                kwargs['offset'] = start + pagetimespagesize
                rows_left = total_rows - pagetimespagesize
                rows = min(rows_left, page_size)
                kwargs['limit'] = rows
                result = dataset._write_to_hdx('all', kwargs, 'id')
                datasets = list()
                if result:
                    no_results = len(result)
                    for datasetdict in result:
                        dataset = Dataset(configuration=configuration)
                        dataset.old_data = dict()
                        dataset.data = datasetdict
                        dataset._dataset_create_resources()
                        datasets.append(dataset)
                    all_datasets += datasets
                    if no_results < rows:
                        break
                else:
                    logger.debug(result)
            names_list = [dataset['name'] for dataset in all_datasets]
            names = set(names_list)
            if len(names_list) != len(names):  # check for duplicates (shouldn't happen)
                all_datasets = None
                attempts += 1
            elif total_rows == max_int:
                all_names = set(Dataset.get_all_dataset_names())  # check dataset names match package_list
                if names != all_names:
                    all_datasets = None
                    attempts += 1
        if attempts == max_attempts and all_datasets is None:
            raise HDXError('Maximum attempts reached for getting all datasets!')
        return all_datasets

    @staticmethod
    def get_all_resources(datasets):
        # type: (List['Dataset']) -> List['Resource']
        """Get all resources from a list of datasets (such as returned by search)

        Args:
            datasets (List[Dataset]): List of datasets

        Returns:
            List[Resource]: List of resources within those datasets
        """
        resources = []
        for dataset in datasets:
            for resource in dataset.get_resources():
                resources.append(resource)
        return resources

    def get_dataset_date_type(self):
        # type: () -> Optional[str]
        """Get type of dataset date (range, date) or None if no date is set

        Returns:
            Optional[str]: Type of dataset date (range, date) or None if no date is set
        """
        dataset_date = self.data.get('dataset_date', None)
        if dataset_date:
            if '-' in dataset_date:
                return 'range'
            else:
                return 'date'
        else:
            return None

    def get_dataset_date_as_datetime(self):
        # type: () -> Optional[datetime]
        """Get dataset date as datetime.datetime object. For range returns start date.

        Returns:
            Optional[datetime.datetime]: Dataset date in datetime object or None if no date is set
        """
        dataset_date = self.data.get('dataset_date', None)
        if dataset_date:
            if '-' in dataset_date:
                dataset_date = dataset_date.split('-')[0]
            return datetime.strptime(dataset_date, '%m/%d/%Y')
        else:
            return None

    def get_dataset_end_date_as_datetime(self):
        # type: () -> Optional[datetime]
        """Get dataset end date as datetime.datetime object.

        Returns:
            Optional[datetime.datetime]: Dataset date in datetime object or None if no date is set
        """
        dataset_date = self.data.get('dataset_date', None)
        if dataset_date:
            if '-' in dataset_date:
                dataset_date = dataset_date.split('-')[1]
                return datetime.strptime(dataset_date, '%m/%d/%Y')
        return None

    @staticmethod
    def _get_formatted_date(dataset_date, date_format=None):
        # type: (Optional[datetime], Optional[str]) -> Optional[str]
        """Get supplied dataset date as string in specified format. 
        If no format is supplied, an ISO 8601 string is returned.

        Args:
            dataset_date (Optional[datetime.datetime]): dataset date in datetime.datetime format 
            date_format (Optional[str]): Date format. None is taken to be ISO 8601. Defaults to None.

        Returns:
            Optional[str]: Dataset date string or None if no date is set
        """
        if dataset_date:
            if date_format:
                return dataset_date.strftime(date_format)
            else:
                return dataset_date.date().isoformat()
        else:
            return None

    def get_dataset_date(self, date_format=None):
        # type: (Optional[str]) -> Optional[str]
        """Get dataset date as string in specified format. For range returns start date.
        If no format is supplied, an ISO 8601 string is returned.

        Args:
            date_format (Optional[str]): Date format. None is taken to be ISO 8601. Defaults to None.

        Returns:
            Optional[str]: Dataset date string or None if no date is set
        """
        dataset_date = self.get_dataset_date_as_datetime()
        return self._get_formatted_date(dataset_date, date_format)

    def get_dataset_end_date(self, date_format=None):
        # type: (Optional[str]) -> Optional[str]
        """Get dataset date as string in specified format. For range returns start date.
        If no format is supplied, an ISO 8601 string is returned.

        Args:
            date_format (Optional[str]): Date format. None is taken to be ISO 8601. Defaults to None.

        Returns:
            Optional[str]: Dataset date string or None if no date is set
        """
        dataset_date = self.get_dataset_end_date_as_datetime()
        return self._get_formatted_date(dataset_date, date_format)

    def set_dataset_date_from_datetime(self, dataset_date, dataset_end_date=None):
        # type: (datetime) -> None
        """Set dataset date from datetime.datetime object

        Args:
            dataset_date (datetime.datetime): Dataset date string
            dataset_end_date (Optional[datetime.datetime]): Dataset end date string

        Returns:
            None
        """
        start_date = dataset_date.strftime('%m/%d/%Y')
        if dataset_end_date is None:
            self.data['dataset_date'] = start_date
        else:
            end_date = dataset_end_date.strftime('%m/%d/%Y')
            self.data['dataset_date'] = '%s-%s' % (start_date, end_date)

    @staticmethod
    def _parse_date(dataset_date, date_format):
        # type: (str, Optional[str]) -> datetime
        """Parse dataset date from string using specified format. If no format is supplied, the function will guess.
        For unambiguous formats, this should be fine.

        Args:
            dataset_date (str): Dataset date string
            date_format (Optional[str]): Date format. If None is given, will attempt to guess. Defaults to None.

        Returns:
            datetime.datetime
        """
        if date_format is None:
            try:
                return parser.parse(dataset_date)
            except (ValueError, OverflowError) as e:
                raisefrom(HDXError, 'Invalid dataset date!', e)
        else:
            try:
                return datetime.strptime(dataset_date, date_format)
            except ValueError as e:
                raisefrom(HDXError, 'Invalid dataset date!', e)

    def set_dataset_date(self, dataset_date, dataset_end_date=None, date_format=None):
        # type: (str, Optional[str]) -> None
        """Set dataset date from string using specified format. If no format is supplied, the function will guess.
        For unambiguous formats, this should be fine.

        Args:
            dataset_date (str): Dataset date string
            dataset_end_date (Optional[str]): Dataset end date string
            date_format (Optional[str]): Date format. If None is given, will attempt to guess. Defaults to None.

        Returns:
            None
        """
        parsed_date = self._parse_date(dataset_date, date_format)
        if dataset_end_date is None:
            self.set_dataset_date_from_datetime(parsed_date)
        else:
            parsed_end_date = self._parse_date(dataset_end_date, date_format)
            self.set_dataset_date_from_datetime(parsed_date, parsed_end_date)

    @staticmethod
    def transform_update_frequency(frequency):
        # type: (str) -> str
        """Get numeric update frequency (as string since that is required field format) from textual representation or
        vice versa (eg. 'Every month' = '30', '30' = 'Every month')

        Args:
            frequency (str): Update frequency in one format

        Returns:
            str: Update frequency in alternative format
        """
        return Dataset.update_frequencies.get(frequency.lower())

    def get_expected_update_frequency(self):
        # type: () -> Optional[str]
        """Get expected update frequency (in textual rather than numeric form)

        Returns:
            Optional[str]: Update frequency in textual form or None if the update frequency doesn't exist or is blank.
        """
        days = self.data.get('data_update_frequency', None)
        if days:
            return Dataset.transform_update_frequency(days)
        else:
            return None

    def set_expected_update_frequency(self, update_frequency):
        # type: (str) -> None
        """Set expected update frequency

        Args:
            update_frequency (str): Update frequency

        Returns:
            None
        """
        try:
            int(update_frequency)
        except ValueError:
            update_frequency = Dataset.transform_update_frequency(update_frequency)
        if not update_frequency:
            raise HDXError('Invalid update frequency supplied!')
        self.data['data_update_frequency'] = update_frequency

    def get_tags(self):
        # type: () -> List[str]
        """Return the dataset's list of tags

        Returns:
            List[str]: List of tags or [] if there are none
        """
        return self._get_tags()

    def add_tag(self, tag):
        # type: (str) -> bool
        """Add a tag

        Args:
            tag (str): Tag to add

        Returns:
            bool: True if tag added or False if tag already present
        """
        return self._add_tag(tag)

    def add_tags(self, tags):
        # type: (List[str]) -> bool
        """Add a list of tag

        Args:
            tags (List[str]): List of tags to add

        Returns:
            bool: Returns True if all tags added or False if any already present.
        """
        return self._add_tags(tags)

    def remove_tag(self, tag):
        # type: (str) -> bool
        """Remove a tag

        Args:
            tag (str): Tag to remove

        Returns:
            bool: True if tag removed or False if not
        """
        return self._remove_hdxobject(self.data.get('tags'), tag, matchon='name')

    def get_location(self):
        # type: () -> List[str]
        """Return the dataset's location

        Returns:
            List[str]: List of locations or [] if there are none
        """
        countries = self.data.get('groups', None)
        if not countries:
            return list()
        return [x['name'] for x in countries]

    def add_other_location(self, hdx_group_name):
        # type: (str) -> None
        """Add a location which is not a country or continent. Value is parsed and compared to existing locations in 
        HDX. If the location is already added, it is ignored.

        Args:
            location (str): Location to add
            exact (Optional[bool]): True for exact matching or False to allow fuzzy matching. Defaults to True.
            alterror (Optional[str]): Alternative error message to builtin if location not found. Defaults to None.

        Returns:
            bool: True if location added or False if location already present
        """
        groups = self.data.get('groups', None)
        if groups:
            if hdx_group_name in [x['name'] for x in groups]:
                return
        else:
            groups = list()
        groups.append({'name': hdx_group_name})
        self.data['groups'] = groups
        return True

    def remove_location(self, location):
        # type: (str) -> bool
        """Remove a location. If the location is already added, it is ignored.

        Args:
            location (str): Location to remove

        Returns:
            bool: True if location removed or False if not
        """
        return self._remove_hdxobject(self.data.get('groups'), location, matchon='name')

    def get_maintainer(self):
        # type: () -> User
        """Get the dataset's maintainer.

         Returns:
             User: Returns dataset's maintainer
        """
        return User.read_from_hdx(self.data['maintainer'], configuration=self.configuration)

    def set_maintainer(self, maintainer):
        # type: (Any) -> None
        """Set the dataset's maintainer.

         Args:
             maintainer (Any): Set the dataset's maintainer either from a User object or a str.
         Returns:
             None
        """
        if isinstance(maintainer, str):
            self.data['maintainer'] = maintainer
        elif isinstance(maintainer, User):
            self.data['maintainer'] = maintainer['name']
        else:
            raise HDXError("Type %s cannot be added as a maintainer!" % type(maintainer).__name__)

    def get_organization(self):
        # type: () -> hdx.data.organization.Organization
        """Get the dataset's organization.

         Returns:
             Organization: Returns dataset's organization
        """
        return hdx.data.organization.Organization.read_from_hdx(self.data['owner_org'], configuration=self.configuration)

    def set_organization(self, organization):
        # type: (Union[Organization,str]) -> None
        """Set the dataset's organization.

         Args:
             organization (Union[Organization,str]): Set the dataset's organization either from an Organization object or a str.
         Returns:
             None
        """
        if isinstance(organization, str):
            self.data['owner_org'] = organization
        elif isinstance(organization, hdx.data.organization.Organization):
            org_id = organization.get('id')
            if org_id is None:
                org_id = organization['name']
            self.data['owner_org'] = org_id
        else:
            raise HDXError("Type %s cannot be added as a organization!" % type(organization).__name__)

    def get_showcases(self):
        # type: () -> List[Showcase]
        """Get any showcases the dataset is in

        Returns:
            List[Showcase]: List of showcases
        """
        assoc_result, showcases_dicts = self._read_from_hdx('showcase', self.data['id'], fieldname='package_id',
                                                            action=hdx.data.showcase.Showcase.actions()['list_showcases'])
        showcases = list()
        if assoc_result:
            for showcase_dict in showcases_dicts:
                showcase = hdx.data.showcase.Showcase(showcase_dict, configuration=self.configuration)
                showcases.append(showcase)
        return showcases

    def _get_dataset_showcase_dict(self, showcase):
        # type: (Union[Showcase,dict,str]) -> dict
        """Get dataset showcase dict

        Args:
            showcase (Union[Showcase,dict,str]): Either a showcase id or Showcase metadata from a Showcase object or dictionary

        Returns:
            dict: dataset showcase dict
        """
        if isinstance(showcase, str):
            return {'package_id': self.data['id'], 'showcase_id': showcase}
        elif isinstance(showcase, hdx.data.showcase.Showcase) or isinstance(showcase, dict):
            return {'package_id': self.data['id'], 'showcase_id': showcase['id']}
        else:
            raise HDXError("Type %s cannot be added as a showcase!" % type(showcase).__name__)

    def add_showcase(self, showcase):
        # type: (Union[Showcase,dict,str]) -> None
        """Add dataset to showcase

        Args:
            showcase (Union[Showcase,dict,str]): Either a showcase id or showcase metadata from a Showcase object or dictionary

        Returns:
            None
        """
        dataset_showcase = self._get_dataset_showcase_dict(showcase)
        showcase = hdx.data.showcase.Showcase({'id': dataset_showcase['showcase_id']}, configuration=self.configuration)
        showcase._write_to_hdx('associate', dataset_showcase, 'package_id')

    def add_showcases(self, showcases):
        # type: (List[Union[Showcase,dict,str]]) -> None
        """Add dataset to multiple showcases

        Args:
            showcases (List[Union[Showcase,dict,str]]): A list of either showcase ids or showcase metadata from Showcase objects or dictionaries

        Returns:
            None
        """
        for showcase in showcases:
            self.add_showcase(showcase)

    def remove_showcase(self, showcase):
        # type: (Union[Showcase,dict,str]) -> None
        """Remove dataset from showcase

        Args:
            showcase (Union[Showcase,dict,str]): Either a showcase id string or showcase metadata from a Showcase object or dictionary

        Returns:
            None
        """
        dataset_showcase = self._get_dataset_showcase_dict(showcase)
        showcase = hdx.data.showcase.Showcase({'id': dataset_showcase['showcase_id']}, configuration=self.configuration)
        showcase._write_to_hdx('disassociate', dataset_showcase, 'package_id')

