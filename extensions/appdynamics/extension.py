# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""AppDynamics Extension
Downloads, installs and configures the AppDynamics agent for PHP
"""
import os
import os.path
import logging
import sys
from subprocess import Popen
from subprocess import PIPE


_log = logging.getLogger('appdynamics')


DEFAULTS = {
    'APPDYNAMICS_HOST': 'download.appdynamics.com',
    'APPDYNAMICS_VERSION': '4.1.0.4',
    'APPDYNAMICS_PACKAGE': 'appdynamics-php-agent-x64-linux-{APPDYNAMICS_VERSION}.tar.bz2',
    'APPDYNAMICS_DOWNLOAD_URL': 'https://s3-us-west-2.amazonaws.com/niksappd/appdynamics-php-agent-x64-linux-4.1.1.0.tar.gz',
    'APPDYNAMICS_STRIP': True
}


class AppDynamicsInstaller(object):
    def __init__(self, ctx):
        self._log = _log
        self._ctx = ctx
        self._detected = False
        self.app_name = None
        self.license_key = None
        try:
            self._log.info("Initializing")
            if ctx['PHP_VM'] == 'php':
                self._merge_defaults()
                self._load_service_info()
                self._load_php_info()
                self._load_appdynamics_info()
        except Exception:
            self._log.exception("Error installing AppDynamics! "
                                "AppDynamics will not be available.")

    def _merge_defaults(self):
        for key, val in DEFAULTS.iteritems():
            if key not in self._ctx:
                self._ctx[key] = val

    def _load_service_info(self):
        services = self._ctx.get('VCAP_SERVICES', {})
        services = services.get('appdynamics', [])
        if len(services) == 0:
            self._log.info("AppDynamics services not detected.")
        if len(services) > 1:
            self._log.warn("Multiple AppDynamics services found, "
                           "credentials from first one.")
        if len(services) > 0:
            service = services[0]
            creds = service.get('credentials', {})
            self.license_key = creds.get('licenseKey', None)
            if self.license_key:
                self._log.debug("AppDynamics service detected.")
                self._detected = True

        self._log.debug("AppDynamics service enabled")
        self.license_key = 'e826ea1a-4ba4-49c1-998a-d243a12e81c5'
        self._detected = True

    def _load_appdynamics_info(self):
        vcap_app = self._ctx.get('VCAP_APPLICATION', {})
        self.app_name = vcap_app.get('name', None)
        self._log.debug("App Name [%s]", self.app_name)

	self.app_name = "PHPECommerce-CloudFoundry"
	self.license_key = "e826ea1a-4ba4-49c1-998a-d243a12e81c5"

        if 'APPDYNAMICS_LICENSE' in self._ctx.keys():
            if self._detected:
                self._log.info("Detected a AppDynamics Service & Manual Key,"
                               " using the manual key.")
            self.license_key = self._ctx['APPDYNAMICS_LICENSE']
            self._detected = True

        if self._detected:
            appdynamics_so_name = 'appdynamics-%s%s.so' % (
                self._php_api, (self._php_zts and 'zts' or ''))
            self.appdynamics_so = os.path.join('@{HOME}', 'appdynamics',
                                            'agent', self._php_arch,
                                            appdynamics_so_name)
            self._log.debug("PHP Extension [%s]", self.appdynamics_so)
            self.log_path = os.path.join('@{HOME}', 'logs',
                                         'appdynamics-daemon.log')
            self._log.debug("Log Path [%s]", self.log_path)
            self.daemon_path = os.path.join(
                '@{HOME}', 'appdynamics', 'daemon',
                'appdynamics-daemon.%s' % self._php_arch)
            self._log.debug("Daemon [%s]", self.daemon_path)
            self.socket_path = os.path.join('@{HOME}', 'appdynamics',
                                            'daemon.sock')
            self._log.debug("Socket [%s]", self.socket_path)
            self.pid_path = os.path.join('@{HOME}', 'appdynamics',
                                         'daemon.pid')
            self._log.debug("Pid File [%s]", self.pid_path)

    def _load_php_info(self):
        self.php_ini_path = os.path.join(self._ctx['BUILD_DIR'],
                                         'php', 'etc', 'php.ini')
        self._php_extn_dir = self._find_php_extn_dir()
        self._php_api, self._php_zts = self._parse_php_api()
        self._php_arch = self._ctx.get('APPDYNAMICS_ARCH', 'x64')
        self._log.debug("PHP API [%s] Arch [%s]",
                        self._php_api, self._php_arch)

    def _find_php_extn_dir(self):
        with open(self.php_ini_path, 'rt') as php_ini:
            for line in php_ini.readlines():
                if line.startswith('extension_dir'):
                    (key, val) = line.strip().split(' = ')
                    return val.strip('"')

    def _parse_php_api(self):
        tmp = os.path.basename(self._php_extn_dir)
        php_api = tmp.split('-')[-1]
        php_zts = (tmp.find('non-zts') == -1)
        return php_api, php_zts

    def should_install(self):
        return self._detected

    def modify_php_ini(self):
	"""
        with open(self.php_ini_path, 'rt') as php_ini:
            lines = php_ini.readlines()
        extns = [line for line in lines if line.startswith('extension=')]
        if len(extns) > 0:
            pos = lines.index(extns[-1]) + 1
        else:
            pos = lines.index('#{PHP_EXTENSIONS}\n') + 1
        lines.insert(pos, 'extension=%s\n' % self.appdynamics_so)
        lines.append('\n')
        lines.append('[appdynamics]\n')
        lines.append('appdynamics.license=%s\n' % self.license_key)
        lines.append('appdynamics.appname=%s\n' % self.app_name)
        lines.append('appdynamics.daemon.logfile=%s\n' % self.log_path)
        lines.append('appdynamics.daemon.location=%s\n' % self.daemon_path)
        lines.append('appdynamics.daemon.port=%s\n' % self.socket_path)
        lines.append('appdynamics.daemon.pidfile=%s\n' % self.pid_path)
        with open(self.php_ini_path, 'wt') as php_ini:
            for line in lines:
                php_ini.write(line)
	"""
        self._log.debug("nothing to do in modify_php_ini")

    def install_phpagent(self):
	os.system("pwd")
	os.system("find ./ -name etc")
	os.system("find ./app -name httpd.conf ")
	os.system("find ./ -name apachectl")
    	exit_code = os.system("mkdir -p ./app/appdynamics/phpini")
	os.system("find ./app/appdynamics/ -name phpini")
	os.system("find ./ -name httpd")
    	#exit_code = os.system("chmod -R 755 ./app; chmod 777 ./app/appdynamics/logs; PATH=$PATH:./app/php/bin/ ./app/appdynamics/install.sh -s -i ./app/appdynamics/phpini -a=appdynamics@bb6604c1-fbe0-400a-a76b-87c26254fe5e 54.245.245.19 443 ecommerce-php-pcf webtier npm-cent7-15")
#	exit_code = os.system("LD_LIBRARY_PATH=$LD_LIBRARY_PATH:./app/httpd/lib ./app/httpd/bin/httpd -k restart -d ./app/httpd ")
#	exit_code = os.system("service httpd restart")
#	exit_code = os.system("./app/httpd/bin/apachectl -k restart -d ./app/httpd")

        if exit_code == 0:
            self._log.debug("install.sh AppDynamics PHP Agent done")
	else:
            self._log.debug("install.sh AppDynamics PHP Agent failed")
            raise RuntimeError("failed running AppDynamics install.sh: exit code: %d" % exit_code)
    	return ()

# Extension Methods
def preprocess_commands(ctx):
    _log.debug("preprocess_commands stage in AppD extension")
    return ()

def service_commands(ctx):
    _log.debug("service_commands stage in AppD extension")
    return {}

def service_environment(ctx):
    return {}


def compile(install):
    appdynamics = AppDynamicsInstaller(install.builder._ctx)
    if appdynamics.should_install():
        _log.info("Installing AppDynamics")
        install.package('APPDYNAMICS')
        _log.info("Configuring AppDynamics in php.ini")
        appdynamics.modify_php_ini()
        _log.info("Installing AppDynamics php agent")
        appdynamics.install_phpagent()
        _log.info("AppDynamics Installed.")
    return 0
