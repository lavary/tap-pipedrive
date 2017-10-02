import os
import singer
import pendulum


logger = singer.get_logger()


class PipedriveStream(object):
    endpoint = ''
    key_properties = []
    state_field = None
    state = None
    schema = ''
    schema_path = 'schemas/{}.json'

    start = 0
    limit = 100
    next_start = 100
    more_items_in_collection = True

    def get_schema(self):
        schema_path = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                   self.schema_path.format(self.schema))
        schema = singer.utils.load_json(schema_path)
        return schema

    def write_schema(self):
        singer.write_schema(self.schema, self.get_schema(), key_properties=self.key_properties)

    def get_name(self):
        return self.endpoint

    def update_state(self, row):
        if self.state_field:
            # nullable update_time breaks bookmarking
            if self.get_row_state(row) is not None:
                current_state = pendulum.parse(self.get_row_state(row))

                if self.state_is_newer_or_equal(current_state):
                    self.state = current_state

    def set_initial_state(self, state, start_date):
        try:
            dt = state['bookmarks'][self.schema][self.state_field]
            if dt is not None:
                self.state = pendulum.parse(dt)
                return

        except (TypeError, KeyError) as e:
            pass

        self.state = start_date

    def has_data(self):
        return self.more_items_in_collection

    def paginate(self, response):
        payload = response.json()

        if 'additional_data' in payload and 'pagination' in payload['additional_data']:
            logger.debug('Paginate: valid response')
            pagination = payload['additional_data']['pagination']
            if 'more_items_in_collection' in pagination:
                self.more_items_in_collection = pagination['more_items_in_collection']

                if 'next_start' in pagination:
                    self.start = pagination['next_start']

        else:
            self.more_items_in_collection = False

        if self.more_items_in_collection:
            logger.debug('Stream {} has more data starting at {}'.format(self.schema, self.start))
        else:
            logger.debug('Stream {} has no more data'.format(self.schema))

    def update_request_params(self, params):
        """
        Non recent stream doesn't modify request params
        """
        return params

    def metrics_http_request_timer(self, response):
        with singer.metrics.http_request_timer(self.schema) as timer:
            timer.tags[singer.metrics.Tag.http_status_code] = response.status_code

    def state_is_newer_or_equal(self, current_state):
        if self.state is None:
            self.state = current_state
            return True

        if current_state >= self.state:
            self.state = current_state
            return True

        return False

    def write_record(self, row):
        if self.record_is_newer_equal_null(row):
            singer.write_record(self.schema, row)
            return True
        return False

    def record_is_newer_equal_null(self, row):
        # no bookmarking in stream or state is null
        if not self.state_field or self.state is None:
            return True

        # state field is null
        if self.get_row_state(row) is None:
            return True

        # newer or equal
        current_state = pendulum.parse(self.get_row_state(row))
        if current_state >= self.state:
            return True

        return False

    def get_row_state(self, row):
        return row[self.state_field]
