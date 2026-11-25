file { '/var/www/ams-demo':
  ensure => directory,
  owner  => 'root',
  group  => 'root',
  mode   => '0755',
}

['portfolio', 'cloud-console', 'storefront'].each |String $app_id| {
  file { "/var/www/ams-demo/${app_id}":
    ensure => directory,
    owner  => 'root',
    group  => 'root',
    mode   => '0755',
  }

  file { "/var/www/ams-demo/${app_id}/index.html":
    ensure => file,
    owner  => 'root',
    group  => 'root',
    mode   => '0644',
    source => "file:///tmp/ams-demo-${app_id}.html",
  }
}

file { '/etc/nginx/conf.d/dummy-app.conf':
  ensure => absent,
}

file { '/etc/nginx/conf.d/ams-demo-apps.conf':
  ensure  => file,
  owner   => 'root',
  group   => 'root',
  mode    => '0644',
  source  => 'file:///tmp/ams-demo-apps.conf',
  require => File['/var/www/ams-demo'],
  notify  => Service['nginx'],
}

service { 'nginx':
  ensure => running,
  enable => true,
}
