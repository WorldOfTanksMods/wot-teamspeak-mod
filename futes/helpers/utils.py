import mock

def mock_was_called_with(mock_obj, *args, **kwargs):
	'''Returns True if 'mock_obj' was ever called with provided arguments.'''
	return mock.call(*args, **kwargs) in mock_obj.call_args_list