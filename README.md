# ros-tls

A simple script to acquire TLS certificates for RouterOS devices using the `lego` Let's Encrypt client and Route53 DNS
to answer a DNS ACME challenge.

## Prerequisites

* The [lego client](https://github.com/xenolf/lego) is installed and in the `PATH`.

* Python 3 is installed (I suggest using a fresh virtualenv).

* A [Route53 hosted zone](http://docs.aws.amazon.com/Route53/latest/DeveloperGuide/CreatingHostedZone.html) has been
created for your desired domain name.

* [IAM credentials](http://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_create_for-user.html) have been created
that can edit the above zone.

* The boto3 library can [pick up AWS credentials](https://boto3.readthedocs.io/en/latest/guide/quickstart.html#configuration)
for your Route53 zone.

* You have an SSH key setup for the configured RouterOS user.

## Running the script

```bash
pip install -r requirements.txt
python3 ros-tls.py
```
