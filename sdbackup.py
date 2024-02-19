import os
import shutil
import subprocess
import re
import sys
from gpiozero import Button, LED
from signal import pause
from datetime import datetime
import threading


def log(message, print_to_screen=False):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_message = f'{timestamp} {message}'

    with open(LOG_FILE, 'a') as log_file:
        log_file.write(log_message + '\n')

    if print_to_screen:
        print(log_message)


def led_flash():
    led = LED(LED_PIN)
    while copying:  # Assuming 'copying' is a variable indicating whether copying is in progress
        led.on()
        sleep(0.5)  # Adjust the duration of each flash as needed
        led.off()
        sleep(0.5)

    led.off()  # Ensure the LED is turned off after copying is done
    log('LED flashed.')


def copy_files(source_loc):
    global copying
    copying = True

    flash_thread = threading.Thread(target=flash_led)
    flash_thread.start()

    try:

        # Read destination path from id.txt on SDCARD or use default
        # sdcard_path = '/media/sdcard/'
        id_file_path = os.path.join(source_loc, 'id.txt')

        if os.path.exists(id_file_path):
            with open(id_file_path, 'r') as id_file:
                destination_path = id_file.read().strip()
                log(f'id.txt found',
                    print_to_screen=PRINT_TO_SCREEN)
        else:
            destination_path = DEFAULT_DESTINATION_PATH
            log(f'id.txt NOT found, using default path',
                print_to_screen=PRINT_TO_SCREEN)

        destination_folder = os.path.join(USB_HDD_PATH, destination_path)

        log(f'Copying files to: {destination_folder}',
            print_to_screen=PRINT_TO_SCREEN)

        # Copy .MP4 files from SDCARD to USB HDD
        for root, dirs, files in os.walk(source_loc):
            for file in files:
                if file.endswith('.MP4'):
                    source_file = os.path.join(root, file)
                    destination_file = os.path.join(destination_folder, file)

                    try:
                        log(f'Attempting to copy "{file}"',
                            print_to_screen=PRINT_TO_SCREEN)
                        shutil.copy2(source_file, destination_file)
                        log(f'File "{file}" copied successfully.',
                            print_to_screen=PRINT_TO_SCREEN)
                    except Exception as e:
                        log(f'Error copying file "{file}": {e}',
                            print_to_screen=PRINT_TO_SCREEN)

    finally:
        copying = False
        flash_thread.join()


def parse_size(size_str):
    # Convert human-readable size string to bytes
    suffixes = {'K': 1024, 'M': 1024**2, 'G': 1024**3, 'T': 1024**4}
    size_str = size_str.upper()
    for suffix, factor in suffixes.items():
        if size_str.endswith(suffix):
            return int(float(size_str[:-1]) * factor)
    return int(size_str)


def find_and_mount(min_size, max_size, mount_point, user_device_name, device_list):
    log(f'Mounting {user_device_name}', print_to_screen=PRINT_TO_SCREEN)
    lsblk_output = subprocess.check_output(
        ['lsblk', '-n', '-b', '-o', 'NAME,SIZE,TYPE']).decode('utf-8')
    lines = lsblk_output.strip().split('\n')

    for line in lines:
        fields = re.split(r'\s+', line.strip())
        device = fields[0]
        device = device.replace('└─', '').replace('─', '')
        size = parse_size(fields[1])
        device_type = fields[2]

        if device_type == 'part' and min_size <= size <= max_size:
            log(
                f'Found {user_device_name} at {device} with size {size / (1024**3):.2f} GB.', print_to_screen=PRINT_TO_SCREEN)
            try:
                subprocess.run(
                    ['sudo', 'mount', f'/dev/{device}', mount_point])
                device_list.append((device, user_device_name))
                log(f'{user_device_name} mounted at {mount_point}.',
                    print_to_screen=PRINT_TO_SCREEN)
                return True
            except subprocess.CalledProcessError as e:
                log(f'Failed to mount {device_path}: {e}',
                    print_to_screen=PRINT_TO_SCREEN)
            return False

    log(f'No suitable {user_device_name} found.',
        print_to_screen=PRINT_TO_SCREEN)
    return False


def unmount_drives(device_list):
    try:
        if not device_list:
            log('No devices to unmount.', print_to_screen=PRINT_TO_SCREEN)
            return

        for device, user_device_name in device_list:
            device_loc = f'/dev/{device}'
            try:
                subprocess.run(['sudo', 'umount', device_loc], check=True)
                # If the subprocess call doesn't raise an exception, log the success
                log(f'{user_device_name} at {device_loc} unmounted successfully.',
                    print_to_screen=PRINT_TO_SCREEN)
            except subprocess.CalledProcessError as e:
                # Log the error if umount command fails
                log(f'Error unmounting {user_device_name} at {device_loc}. Error: {e}',
                    print_to_screen=PRINT_TO_SCREEN)

    except Exception as ex:
        # Log any unexpected exceptions during the unmount process
        log(f'An unexpected error occurred during unmounting. Error: {ex}',
            print_to_screen=PRINT_TO_SCREEN)

# Example usage:
# unmount_drives(['/dev/sdX', '/dev/sdY'])


# GLOBAL VARIABLES
LOG_FILE = '/home/pi/sdbackup/sdbackup.log'
TRIGGER_PIN = 17
LED_PIN = 21
USB_HDD_PATH = '/media/usbhdd/'
DEFAULT_DESTINATION_PATH = 'sdbackup/other/'
PRINT_TO_SCREEN = True

# SD CARD VARIABLES
sd_min_size_gb = 50
sd_max_size_gb = 500
sd_mount_point = '/media/sdcard'
sd_name = 'SD_CARD'

# HD CARD VARIABLES
hd_min_size_gb = 1500
hd_max_size_gb = 3000
hd_mount_point = '/media/usbhdd/'
hd_name = 'USB_HDD'


def on_trigger():
    log('Trigger event detected.', print_to_screen=PRINT_TO_SCREEN)

    unmount_list = []

    print('')
    find_and_mount(sd_min_size_gb * 1024**3,
                   sd_max_size_gb * 1024**3, sd_mount_point, sd_name, unmount_list)

    print('')
    find_and_mount(hd_min_size_gb * 1024**3,
                   hd_max_size_gb * 1024**3, hd_mount_point, hd_name, unmount_list)

    print('')
    copy_files(sd_mount_point)

    print('')
    unmount_drives(unmount_list)


if len(sys.argv) > 1 and sys.argv[1] == '-o':
    on_trigger()
else:
    button = Button(TRIGGER_PIN)
    button.when_pressed = on_trigger

    log('Script started.', print_to_screen=PRINT_TO_SCREEN)
    pause()
