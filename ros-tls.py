#!/bin/env python3

from colorama import init, Fore, Style
from paramiko.client import SSHClient
import paramiko
import requests
import os.path
import shutil
import subprocess
import re

init()

#
# Configuration
#

HOSTS = [
    'ros.device.domain.com',
    'ros.device2.domain.com'
]
ADMIN_EMAIL = 'me@domain.com'
SSH_USER = 'myuser'
SSH_KEY_PATH = '/home/myuser/.ssh/id_rsa'

#
# Here be dragons!
#

__VERSION__ = '0.0.0.1'
paramiko.util.log_to_file('ssh.log')
MATCH_CERTIFICATE = re.compile('certificate=(\\S+)')


def renew_certificate(lego_exe_path, host, email):
    """Use the lego client to request a new Let's Encrypt certificate."""
    result = subprocess.call(
        [lego_exe_path, '--domains', host, '--email', email, '--accept-tos', '--dns', 'route53', 'run'])

    if result == 0:
        print(Fore.GREEN + '--> Renewed certificate!')
    else:
        print(Fore.RED + '--> Failed to renew certificate!')


def connect_via_ssh(ssh_user, ssh_key_path):
    client = SSHClient()
    client.load_system_host_keys()
    client.connect(host, username=ssh_user, key_filename=ssh_key_path, allow_agent=False, look_for_keys=False)

    return client


def upload_certificate(sftp_client, certificate_path):
    print('--> Uploading certificate')

    with open(certificate_path, 'r') as cert:
        with sftp_client.open(host + '.crt', 'w') as remote_cert:
            remote_cert.write(cert.read())

    print('--> Uploaded certificate')


def upload_key(sftp_client, private_key_path):
    print('--> Uploading private key')

    with open(private_key_path, 'r') as private_key:
        with sftp_client.open(host + '.key', 'w') as remote_key:
            remote_key.write(private_key.read())

    print('--> Uploaded private key')


def get_current_certificate(client):
    stdin, stdout, stderr = client.exec_command('/ip service print detail where name=www-ssl')

    output = ''.join(stdout.readlines())
    certificates = MATCH_CERTIFICATE.findall(output)

    if len(certificates) == 0:
        print('--> No current certificate found')

        return None
    else:
        if certificates[0] != '*1':
            print('--> Configured to use certificate "%s"' % certificates[0])

            return certificates[0]
        else:
            return None


def delete_certificate(client, certificate):
    print('--> Deleting certificate %s' % certificate)
    client.exec_command('/certificate remove ' + certificate)

    crl_path = certificate.replace('crt', 'crl')

    print('--> Deleting certificate revocation list %s' % certificate)
    client.exec_command('/certificate remove ' + crl_path)


def import_certificate(client, host):
    certificate_path = host + '.crt'

    print('--> Importing certificate')
    client.exec_command('/certificate import passphrase="" file-name=' + certificate_path)
    print('--> Imported certificate')


def import_key(client, host):
    key_path = host + '.key'

    print('--> Importing private key')
    client.exec_command('/certificate import passphrase="" file-name=' + key_path)
    print('--> Imported private key')


def set_new_certificate(client, host):
    new_certificate_name = host + '.crt_0'

    print('--> Setting new certificate to %s' % new_certificate_name)
    client.exec_command('/ip service set www-ssl certificate=' + new_certificate_name)
    print('--> New certificate installed')


def replace_certificate(ssh_user, ssh_key_path, host):
    """Upload an X509 certificate to the RouterOS device."""
    certificate_path = os.path.join('.lego', 'certificates', host + '.crt')
    private_key_path = os.path.join('.lego', 'certificates', host + '.key')

    if os.path.exists(certificate_path) and os.path.exists(private_key_path):
        client = connect_via_ssh(ssh_user, ssh_key_path)
        sftp_client = client.open_sftp()

        upload_certificate(sftp_client, certificate_path)
        upload_key(sftp_client, private_key_path)

        current_certificate = get_current_certificate(client)

        if current_certificate:
            delete_certificate(client, current_certificate)

        import_certificate(client, host)
        import_key(client, host)

        set_new_certificate(client, host)

        client.close()
    else:
        print(Fore.RED + '--> Could not find certificate')


print('ros-tls ' + Style.BRIGHT + 'v' + __VERSION__ + Style.RESET_ALL)

lego_exe_path = shutil.which('lego')

if lego_exe_path is None:
    exit(Fore.RED + 'lego command not found - is it installed?')

for host in HOSTS:
    print('-> Checking for valid certificate on %s' % host)

    try:
        r = requests.get('https://' + host)

        print('-> Certificate appears to be OK - doing nothing')
    except requests.exceptions.SSLError:
        print('-> Certificate needs renewing (or other SSL error)')

        renew_certificate(lego_exe_path, host, ADMIN_EMAIL)
        replace_certificate(SSH_USER, SSH_KEY_PATH, host)
    except requests.exceptions.ConnectionError:
        exit(Fore.RED + 'Failed to lookup host %s!' % host)
