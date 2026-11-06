"""Let the game process pointer hover before pressing, without user movement."""
import time


def deliver_click(send,ready,pause=time.sleep):
    if not ready():return False
    send('move')
    pause(.06)
    if not ready():return False
    try:
        send('down')
        pause(.025)
    finally:
        # Always release, including after focus changes or a failed press.
        send('up')
    return True
