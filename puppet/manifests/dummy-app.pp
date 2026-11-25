class dummy_app {
  file { '/var/www/dummy-app':
    ensure => directory,
    owner  => 'root',
    group  => 'root',
    mode   => '0755',
  }

  file { '/var/www/dummy-app/index.html':
    ensure => file,
    owner  => 'root',
    group  => 'root',
    mode   => '0644',
    source => 'file:///tmp/dummy-app-index.html',
  }

  file { '/etc/nginx/conf.d/dummy-app.conf':
    ensure  => file,
    owner   => 'root',
    group   => 'root',
    mode    => '0644',
    content => "server {\n    listen 8080;\n    listen [::]:8080;\n    server_name _;\n    root /var/www/dummy-app;\n    index index.html;\n    location / { try_files \$uri \$uri/ /index.html; }\n}\n",
    notify  => Service['nginx'],
  }

  service { 'nginx':
    ensure => running,
    enable => true,
  }
}

include dummy_app
