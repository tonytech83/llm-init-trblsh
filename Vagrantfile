Vagrant.configure("2") do |config|
  config.vm.box = "shekeriev/ubuntu-24.04"
  config.vm.box_version = "24.04.3.20260201"

  config.vm.define "target" do |target|
    target.vm.hostname = "target.concept.lab"
    target.vm.network "private_network", ip: "192.168.56.13"
    target.vm.synced_folder "vagrant/", "/vagrant"
    target.vm.provision "shell", path: "scripts/add-hosts.sh"
		target.vm.provision "shell", path: "scripts/install-and-setup-alloy.sh"
    target.vm.provider "virtualbox" do |vbox|
      vbox.name = "concept-target"
      vbox.cpus = 1
      vbox.memory = 1024
    end
  end
  
  config.vm.define "monitor" do |monitor|
    monitor.vm.hostname = "monitor.concept.lab"
    monitor.vm.network "private_network", ip: "192.168.56.14"
    monitor.vm.synced_folder "vagrant/", "/vagrant"
    monitor.vm.provision "shell", path: "scripts/add-hosts.sh"
		monitor.vm.provision "shell", path: "scripts/install-and-setup-alertmanager.sh"
		monitor.vm.provision "shell", path: "scripts/install-and-setup-loki.sh"
		monitor.vm.provision "shell", path: "scripts/install-and-setup-grafana.sh"
    monitor.vm.provider "virtualbox" do |vbox|
      vbox.name = "concept-monitor"
      vbox.cpus = 2
      vbox.memory = 2048
    end
  end

	config.vm.define "troubleshooter" do |troubleshooter|
		troubleshooter.vm.hostname = "troubleshooter.concept.lab"
		troubleshooter.vm.network "private_network", ip: "192.168.56.15"
		troubleshooter.vm.synced_folder "vagrant/", "/vagrant"
		troubleshooter.vm.provision "shell", path: "scripts/add-hosts.sh"
		troubleshooter.vm.provision "shell", path: "scripts/set-and-copy-ssh-key.sh"
		# troubleshooter.vm.provision "shell", path: "scripts/install-docker.sh"
    # troubleshooter.vm.provision "shell", path: "scripts/install-docker-registry.sh"
		# troubleshooter.vm.provision "shell", path: "scripts/install-gitea.sh"
		# troubleshooter.vm.provision "shell", path: "scripts/setup-gitea.sh"
    troubleshooter.vm.provider "virtualbox" do |vbox|
      vbox.name = "concept-troubleshooter"
      vbox.cpus = 2
      vbox.memory = 4096
    end
	end

end