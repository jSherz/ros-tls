#!/bin/env python3
import datetime

import OpenSSL
from colorama import init, Fore, Style
from paramiko.client import SSHClient
import paramiko
import requests
import os.path
import shutil
import subprocess
import re
import json
import sys
import ssl

init()


#
# Configuration
#


def read_config():
    try:
        with open('config.json') as f:
            return json.load(f)
    except IOError:
        raise Exception("create a config.json - see config.json.example")


#
# Here be dragons!
#

__VERSION__ = '0.0.0.1'
paramiko.util.log_to_file('ssh.log')
MATCH_CERTIFICATE = re.compile('certificate=(\\S+)')


def run_command(client, command):
    _, stdout, stderr = client.exec_command(command)
    print(''.join(stdout.readlines()))
    print(''.join(stderr.readlines()))


def renew_certificate(host, lego_exe_path, email):
    """Use the lego client to request a new Let's Encrypt certificate."""
    result = subprocess.call(
        [lego_exe_path, '--domains', host, '--email', email, '--accept-tos', '--dns', 'route53', 'run'])

    if result == 0:
        print(Fore.GREEN + '--> Renewed certificate!' + Fore.RESET)
        return True
    else:
        print(Fore.RED + '--> Failed to renew certificate!' + Fore.RESET)
        return False


def connect_via_ssh(host, ssh_user, ssh_key_path):
    client = SSHClient()
    client.load_system_host_keys()
    client.connect(host, username=ssh_user, key_filename=ssh_key_path, allow_agent=False, look_for_keys=False)

    return client


def upload_certificate(host, sftp_client, certificate_path):
    print('--> Uploading certificate')

    with open(certificate_path, 'r') as cert:
        with sftp_client.open(host + '.crt', 'w') as remote_cert:
            remote_cert.write(cert.read())

    print('--> Uploaded certificate')


def upload_key(host, sftp_client, private_key_path):
    print('--> Uploading private key')

    with open(private_key_path, 'r') as private_key:
        with sftp_client.open(host + '.key', 'w') as remote_key:
            remote_key.write(private_key.read())

    print('--> Uploaded private key')


def get_current_certificate(client):
    _, stdout, stderr = client.exec_command('/ip service print detail where name=www-ssl')

    output = ''.join(stdout.readlines())
    certificates = MATCH_CERTIFICATE.findall(output)

    if len(certificates) == 0:
        print('--> No current certificate found')

        return None
    else:
        if certificates[0] != '*1' and certificates[0] != 'none':
            print('--> Configured to use certificate "%s"' % certificates[0])

            return certificates[0]
        else:
            return None


def delete_certificate(client, certificate):
    print('--> Deleting certificate %s' % certificate)
    run_command(client, '/certificate remove ' + certificate)

    crl_path = certificate.replace('crt', 'crl')

    print('--> Deleting certificate revocation list %s' % certificate)
    run_command(client, '/certificate remove ' + crl_path)


def import_certificate(host, client):
    certificate_path = host + '.crt'

    print('--> Importing certificate')
    run_command(client, '/certificate import passphrase="" file-name=' + certificate_path)
    print('--> Imported certificate')


def import_key(host, client):
    key_path = host + '.key'

    print('--> Importing private key')
    run_command(client, '/certificate import passphrase="" file-name=' + key_path)
    print('--> Imported private key')


def set_new_certificate(host, client):
    new_certificate_name = host + '.crt_0'

    print('--> Setting new certificate to %s' % new_certificate_name)
    run_command(client, '/ip service set www-ssl certificate=' + new_certificate_name)
    print('--> New certificate installed')


def replace_certificate(host, ssh_user, ssh_key_path):
    """Upload an X509 certificate to the RouterOS device."""
    certificate_path = os.path.join('.lego', 'certificates', host + '.crt')
    private_key_path = os.path.join('.lego', 'certificates', host + '.key')

    if os.path.exists(certificate_path) and os.path.exists(private_key_path):
        client = connect_via_ssh(host, ssh_user, ssh_key_path)
        sftp_client = client.open_sftp()

        upload_certificate(host, sftp_client, certificate_path)
        upload_key(host, sftp_client, private_key_path)

        current_certificate = get_current_certificate(client)

        if current_certificate:
            delete_certificate(client, current_certificate)

        import_certificate(host, client)
        import_key(host, client)

        set_new_certificate(host, client)

        client.close()
    else:
        print(Fore.RED + '--> Could not find certificate' + Fore.RESET)


def check_hosts():
    print('ros-tls ' + Style.BRIGHT + 'v' + __VERSION__ + Style.RESET_ALL)

    if sys.version_info[0] != 3:
        exit(Fore.RED + 'python 3 is required')

    config = read_config()

    lego_exe_path = shutil.which('lego')

    if lego_exe_path is None:
        exit(Fore.RED + 'lego command not found - is it installed?')

    for host in config['hosts']:
        print('-> Checking for valid certificate on %s' % host)

        try:
            requests.get('https://' + host)

            certificate = ssl.get_server_certificate((host, 443))
            parsed_certificate = OpenSSL.crypto.load_certificate(OpenSSL.crypto.FILETYPE_PEM, certificate)

            not_after = datetime.datetime.strptime(parsed_certificate.get_notAfter().decode('utf-8'), "%Y%m%d%H%M%SZ")
            now = datetime.datetime.now()

            if not_after - now <= datetime.timedelta(days=15):
                print('-> Certificate needs renewing (expires soon)')

                renewed = renew_certificate(host, lego_exe_path, config['adminEmail'])

                if renewed:
                    replace_certificate(host, config['sshUser'], config['sshKeyPath'])
            else:
                print('-> Certificate appears to be OK - doing nothing')
        except requests.exceptions.SSLError:
            print('-> Certificate needs renewing (or other SSL error)')

            renewed = renew_certificate(host, lego_exe_path, config['adminEmail'])

            if renewed:
                replace_certificate(host, config['sshUser'], config['sshKeyPath'])
        except requests.exceptions.ConnectionError as e:
            print(e)
            exit((Fore.RED + 'Failed to connect to host %s!' + Fore.RESET) % host)


check_hosts()
