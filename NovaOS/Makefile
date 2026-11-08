# NovaOS – skróty
.PHONY: iso debs test smoke docker qemu qemu-bios clean distclean

iso:            ## Zbuduj NovaOS.iso (wymaga root)
	sudo -E ./scripts/build-iso.sh

docker:         ## Zbuduj NovaOS.iso w kontenerze (Docker/Podman)
	sudo -E ./scripts/docker-build.sh

debs:           ## Zbuduj tylko pakiety novaos-*.deb
	./scripts/make-debs.sh

test:           ## Testy jednostkowe i walidacja konfiguracji
	python3 -m pytest -q tests/

smoke:          ## Uruchom wszystkie aplikacje bez ekranu i zapisz zrzuty
	QT_QPA_PLATFORM=offscreen python3 tests/smoke_apps.py out/screenshots

qemu:           ## Uruchom ISO w QEMU (UEFI)
	./scripts/test-qemu.sh

qemu-bios:      ## Uruchom ISO w QEMU (BIOS)
	./scripts/test-qemu.sh --bios

clean:          ## Usuń katalog roboczy (zostaw out/)
	sudo rm -rf work

distclean: clean
	rm -rf out
