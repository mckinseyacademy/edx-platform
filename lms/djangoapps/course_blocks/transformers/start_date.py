"""
Start Date Transformer implementation.
"""

from datetime import datetime
from pytz import UTC

from lms.djangoapps.courseware.access_utils import check_start_date
from openedx.core.djangoapps.content.block_structure.transformer import (
    BlockStructureTransformer,
    FilteringTransformerMixin
)
from xmodule.course_metadata_utils import DEFAULT_START_DATE

from .utils import collect_merged_date_field


class StartDateTransformer(FilteringTransformerMixin, BlockStructureTransformer):
    """
    A transformer that enforces the 'start' and 'days_early_for_beta'
    fields on blocks by removing blocks from the block structure for
    which the user does not have access. The 'start' field on a
    block is percolated down to its descendants, so that all blocks
    enforce the 'start' field from their ancestors.  The assumed
    'start' value for a block is then the maximum of its parent and its
    own.

    For a block with multiple parents, the assumed parent start date
    value is a computed minimum of the start dates of all its parents.
    So as long as one parent chain allows access, the block has access.

    Staff users are exempted from visibility rules.
    """
    WRITE_VERSION = 1
    READ_VERSION = 1
    MERGED_START_DATE = 'merged_start_date'

    @classmethod
    def name(cls):
        """
        Unique identifier for the transformer's class;
        same identifier used in setup.py.
        """
        return "start_date"

    @classmethod
    def _get_merged_start_date(cls, block_structure, block_key):
        """
        Returns the merged value for the start date for the block with
        the given block_key in the given block_structure.
        """
        return block_structure.get_transformer_block_field(
            block_key, cls, cls.MERGED_START_DATE, False
        )

    @classmethod
    def collect(cls, block_structure):
        """
        Collects any information that's necessary to execute this
        transformer's transform method.
        """
        block_structure.request_xblock_fields('days_early_for_beta')

        collect_merged_date_field(
            block_structure,
            transformer=cls,
            xblock_field_name='start',
            merged_field_name=cls.MERGED_START_DATE,
            default_date=DEFAULT_START_DATE,
            func_merge_parents=min,
            func_merge_ancestors=max,
        )

    def transform_block_filters(self, usage_info, block_structure):
        # Users with staff access bypass the Start Date check.
        if usage_info.has_staff_access or usage_info.allow_start_dates_in_future:
            return [block_structure.create_universal_filter()]

        now = datetime.now(UTC)

        removal_condition = lambda block_key: not check_start_date(
            usage_info.user,
            block_structure.get_xblock_field(block_key, 'days_early_for_beta'),
            self._get_merged_start_date(block_structure, block_key),
            usage_info.course_key,
            now=now,
        )
        return [block_structure.create_removal_filter(removal_condition)]


class StartDateFieldTransformer(BlockStructureTransformer):
    """
    A transformer that adds 'start' date to course blocks.
    """
    WRITE_VERSION = 1
    READ_VERSION = 1
    MERGED_START_DATE = 'merged_start_date'

    @classmethod
    def name(cls):
        """
        Unique identifier for the transformer's class;
        same identifier used in setup.py.
        """
        return "start_date_field"

    @classmethod
    def collect(cls, block_structure):
        """
        Collects any information that's necessary to execute this
        transformer's transform method.
        """
        collect_merged_date_field(
            block_structure,
            transformer=cls,
            xblock_field_name='start',
            merged_field_name=cls.MERGED_START_DATE,
            default_date=DEFAULT_START_DATE,
            func_merge_parents=min,
            func_merge_ancestors=max,
        )

    def transform(self, usage_info, block_structure):
        """
        Modify block structure by adding start date field.
        """
        for block_key in block_structure.topological_traversal():
            block_structure.set_transformer_block_field(
                block_key,
                self,
                'start',
                block_structure.get_transformer_block_field(block_key, self, self.MERGED_START_DATE, False)
            )
