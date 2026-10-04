class ServiceError(Exception):
    """Base for all service-layer errors that routes know how to translate."""


class EmailAlreadyRegisteredError(ServiceError):
    pass


class InvalidCredentialsError(ServiceError):
    pass


class InactiveUserError(ServiceError):
    pass


class InvalidRefreshTokenError(ServiceError):
    pass


class DuplicateCollectionNameError(ServiceError):
    pass


class DocumentNotFoundError(ServiceError):
    pass


class ConversationNotFoundError(ServiceError):
    pass
