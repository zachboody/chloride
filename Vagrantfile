Vagrant.configure("2") do |config|
  config.vm.box = "ubuntu/trusty64"

  config.vm.network :forwarded_port, guest: 8000, host: 8000

  # Set virtual machine memory size
  config.vm.provider :virtualbox do |vbox|
    vbox.customize ["modifyvm", :id, "--memory", 2048]
  end

  config.vm.provision :shell, :path => "vagrantcfg/init.sh"
end
