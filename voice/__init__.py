"""ARGUS voice: the layer between an operator's speech and the world model.

Hearing and speaking happen through the AI gateway, so no model or provider
is named here. Orders reach the world model through the same public
interfaces every application uses, carrying the operator's own credentials,
so a voice order is auditable exactly like a map order.

Voice executes nothing without a readback confirmation. That is the whole
safety design and it has no exceptions.
"""
