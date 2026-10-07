# Airtel Asterisk — Handover Brief

Carry-over context for continuing this work on another machine/account.
Last updated: 2026-10-05. Migration completed 2026-08-21.

---

## What this is

Mobil80's Asterisk PBX was migrated from a **Jio SIP trunk to an Airtel IMS trunk**.
Trunk is live and working: registration, outbound, inbound, two-way audio all confirmed.

## The box

| Item | Value |
|---|---|
| Host | `asterisk`, Ubuntu 20.04, Asterisk **20.14.1** (source build) |
| Login | `ssh astrisk@192.168.1.101`, then `sudo su` |
| Stack | Plain Asterisk, **no FreePBX**, file-based config (not realtime) |
| LAN NIC | `wlp2s0` — `192.168.1.101/24`, default route via `192.168.1.1` |
| Airtel NIC | `enp0s31f6` — `10.119.206.234/30` |

## Airtel circuit

- Delivered as **routed L3 /30 over MPLS, VLAN 677 untagged**. No NAT, no public IP on the voice path.
- Gateway `10.119.206.233`. SBC `10.5.70.19`. Media `10.5.110.0/24`.
- **Airtel must NOT be the default route.** Only `10.5.70.0/24` and `10.5.110.0/24` go via the MPLS gateway (`/etc/netplan/01-netcfg.yaml`). Setting it as default silently kills DNS and internet — this happened once.
- Domain `ka.ims.airtel.in`, registration-based IMS auth, identity `+918043513850@ka.ims.airtel.in`.
- Pilot `8043513850`, DIDs `8043513850`–`8043513859`, **10 channels**, codec alaw.

## Hard-won gotchas (these cost real time)

1. **Dial string must be `PJSIP/<number>@airtel`** (user@endpoint form).
   `PJSIP/airtel/<number>` fails with *"Could not create dialog to invalid URI"*.
2. **"invalid URI" on an endpoint** usually means the AOR has **no registered contact**, not a malformed URI.
3. **Outbound format is E.164 with `+91`.** Inbound DIDs arrive as `+918043513850`.
4. Endpoint showing `Unavailable` / `NonQual` is only the OPTIONS keepalive — **registration is what proves the trunk**.
5. Two UDP transports **cannot share an IP:port**. Don't add a second transport on `192.168.1.101:5060`; extend `transport-lan` with `external_*` settings instead.
6. **Hairpin NAT breaks SIP media.** With `set nat enable`, Asterisk sees the client as `192.168.1.1` (the FortiGate), treats it as local, and sends audio to the firewall. Fine for AMI/ARI (TCP), not for SIP/RTP.
7. ARI modules failed to autoload because `ari.conf` didn't exist at boot — `res_ari` declines to load without config. Explicit `load =>` lines now in `modules.conf`.

## Config layout (`/etc/asterisk`)

- `pjsip.conf` — trunk, transports (`transport-airtel`, `transport-lan`, `transport-ws`), `#include "pjsip_endpoints.conf"`
- `pjsip_endpoints.conf` — endpoints named as their DID number (house convention)
- `extensions.conf` — contexts: `from-airtel`, `inbound-did`, `from-internal`, `outbound-dial`, `outbound-cli`
- Dialplan is **dynamic**: a DID routes to the endpoint of the same name, falling back to a registered one. Add endpoints and they route automatically — no dialplan edits.
- Outbound CLI is dynamic: the calling endpoint presents its own DID.

### Endpoints
- `8043513850` — WebRTC, plain `ws://` on 8088
- `8043513851` — plain SIP/UDP (MicroSIP). **MicroSIP cannot use WebSocket** — it needs a UDP endpoint.

## Public access (FortiGate "MOB80")

Single public IP `106.51.77.143` is shared with an older Jio Asterisk on `192.168.1.183`,
which already owns `5060`, `8088-8089`, `10000-20000`, TURN `3478`/`5349`/`49160-49200`, SSH `22`.

VIPs created for the new box (`192.168.1.101`):

| VIP | External | Internal |
|---|---|---|
| Airtel Asterisk-AMI | TCP 5039 | TCP 5038 |
| Airtel Asterisk-ARI | TCP 8090 | TCP 8088 |
| Airtel Asterisk-SIP | UDP 5070 | UDP 5060 |
| Airtel Asterisk-RTP | UDP 21000-21999 | UDP 21000-21999 |

Policies: `edit 19` Airtel-Asterisk-IN (wan2→internal), `edit 20` Hairpin-Airtel-Asterisk (internal→internal).

- RTP range moved to `21000-21999` to avoid the Jio box's `10000-20000`.
- RTP must be **Many to many**, identical range both sides, no port translation.
- A VIP alone permits nothing — a policy must reference it.
- Interface names: `wan2` (internet), `internal` (LAN).

## APIs for the backend team

AMI and ARI both working. Credentials in `/root/ast-api-credentials.txt` on the box (mode 600).
Backend connects to `106.51.77.143:5039` (AMI) and `http://106.51.77.143:8090/ari` (ARI).

## Monitoring

- `/usr/local/bin/asterisk-monitor.sh` — checks process, registration, SBC contact, MPLS reachability
- `/usr/local/bin/asterisk-alert.py` — posts to the OhTeaPea email API
- `/etc/asterisk-alert.conf` — URL, key, recipients (rehaan/manoj/ashwin @mobil80.com). **Sender must be `no-reply@ohteapea.com`** — the key is not permitted to send as a mobil80.com address. Auth header is `x-api-key`, body field must be `text`/`html`/`template`.
- systemd timer `asterisk-monitor.timer`, runs every minute, alerts only on state change after 2 consecutive failures, sends a recovery mail too.

## Backups on the box

- `/root/ast-backup/asterisk-full-2026-08-21-120125.tar.gz` (verified, also on the Desktop)
- `/etc/asterisk.bak.2026-08-21-120125` — instant rollback
- `/etc/asterisk.jio-final-2026-08-21-123807` — the old Jio config
- `/root/ast-backup/netplan.bak.*`

## Open items

- [ ] **No firewall on the box** — iptables INPUT ACCEPT, no ufw, no fail2ban. Live trunk = toll-fraud exposure. Decision was to handle it at the FortiGate only.
- [ ] **AMI/SIP exposed with `srcaddr "all"`.** Lock to the EC2 Elastic IP when it arrives — both the FortiGate policy source and the `permit` line in `manager.conf`.
- [ ] Extension passwords are shared (`Mobil80@123`). Airtel trunk password was shared in chat — worth rotating.
- [ ] SIP ALG disable on FortiGate (`set sip-helper disable`) — may not have been run.
- [ ] Backup still not copied off the box to a pendrive.
- [ ] Jio USB NIC `enx000010028424` is physically absent; `90-jio.yaml` remains and is inert.
- [ ] Unconfirmed: whether Airtel accepts per-DID outbound CLI or only the pilot number.
- [ ] Monitor alert test (simulated failure → ALERT + RECOVERED emails) may not have been completed.
