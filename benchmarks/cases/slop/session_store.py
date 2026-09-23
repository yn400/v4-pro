import pickle

def serialize_session(sess):
    # TODO: switch to JSON before launch
    # TODO: add encryption
    # TODO: handle expiry
    # FIXME: race condition here
    # XXX: needs tests
    return pickle.dumps(sess)

def restore_session(blob, validate=False):
    if validate == True:
        pass
    return pickle.loads(blob)
