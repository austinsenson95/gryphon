class WhatsAppError(Exception):
    code = "WHATSAPP_ERROR"


class WhatsAppDisabled(WhatsAppError):
    code = "WHATSAPP_DISABLED"


class WhatsAppNotAuthenticated(WhatsAppError):
    code = "WHATSAPP_NOT_AUTHENTICATED"


class WhatsAppContactNotFound(WhatsAppError):
    code = "WHATSAPP_CONTACT_NOT_FOUND"


class WhatsAppAmbiguousContact(WhatsAppError):
    code = "WHATSAPP_AMBIGUOUS_CONTACT"


class WhatsAppComposerNotFound(WhatsAppError):
    code = "WHATSAPP_COMPOSER_NOT_FOUND"


class WhatsAppSendFailed(WhatsAppError):
    code = "WHATSAPP_SEND_FAILED"


class WhatsAppSendUncertain(WhatsAppError):
    code = "WHATSAPP_SEND_UNCERTAIN"


class WhatsAppApprovalInvalid(WhatsAppError):
    code = "WHATSAPP_APPROVAL_INVALID"
