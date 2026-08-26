"""Centralized resilient locator candidates for WhatsApp Web."""

SEARCH_SELECTORS = (
    '[aria-label="Search input textbox"]',
    '[data-testid="chat-list-search"] [contenteditable="true"]',
    'div[contenteditable="true"][role="textbox"][data-tab="3"]',
)
CHAT_LIST_SELECTORS = ('[aria-label="Chat list"]', '#pane-side')
QR_SELECTORS = ('canvas[aria-label*="Scan"]', '[data-ref] canvas', '[data-testid="qrcode"]')
COMPOSER_SELECTORS = (
    'footer div[contenteditable="true"][role="textbox"]',
    '[aria-label="Type a message"]',
    'div[contenteditable="true"][data-tab="10"]',
)
CHAT_TITLE_SELECTORS = ('header [title]', 'header span[dir="auto"]')
SEND_SELECTORS = ('button[aria-label="Send"]', '[data-testid="send"]')
