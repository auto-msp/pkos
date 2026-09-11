#!/usr/bin/env bash
# =============================================================================
#  PKOS SESSION FORENSICS  --  STRICTLY READ-ONLY
#  Who is logged in, how they got there, and is anything acting as a user
#  without being one.
#
#  SAFETY: reads only. No file is created, modified or deleted. No process is
#  killed. No service touched. No network call. No secret VALUE is printed --
#  SSH keys appear as FINGERPRINTS only, never key material.
#
#  Run:  bash pkos-session-forensics.sh            (root recommended)
#        bash pkos-session-forensics.sh > baseline-$(date -u +%Y%m%d).txt
# =============================================================================

H(){ printf "\n\033[1m== %s ==\033[0m\n" "$1" 2>/dev/null || printf "\n== %s ==\n" "$1"; }
have(){ command -v "$1" >/dev/null 2>&1; }
T(){ timeout 15 "$@" 2>/dev/null; }
IS_ROOT=0; [ "$(id -u)" = 0 ] && IS_ROOT=1

echo "PKOS SESSION FORENSICS"
echo "host=$(hostname)  utc=$(date -u +%FT%TZ)  root=$IS_ROOT  uptime=$(uptime -p 2>/dev/null)"

# --------------------------------------------------------------------------
H "1. LIVE SESSIONS (what 'uptime' is counting)"
echo "-- who -a --";        T who -a
echo; echo "-- w (idle + current command) --"; T w
echo; echo "-- utmp session count --"; printf "  users in utmp: %s\n" "$(T who | wc -l)"

if have loginctl; then
  echo; echo "-- systemd-logind sessions --"; T loginctl list-sessions
  echo "   (logind is authoritative; utmp can hold STALE entries from crashed"
  echo "    sessions. A big gap between the two counts usually means stale utmp,"
  echo "    not intruders.)"
fi

# --------------------------------------------------------------------------
H "2. TERMINAL MULTIPLEXERS -- the usual explanation for a high user count"
for d in /tmp/tmux-*; do [ -d "$d" ] && { echo "  socket dir: $d"; T ls -la "$d"; }; done
have tmux   && { echo "-- tmux sessions --";   T tmux ls; }
have screen && { echo "-- screen sessions --"; T screen -ls; }
echo "  Each attached pane can register its own utmp entry. 15 'users' is very"
echo "  often one person with many panes -- confirm before alarming yourself."

# --------------------------------------------------------------------------
H "3. ESTABLISHED SSH CONNECTIONS -- the real remote peers, right now"
if have ss; then
  T ss -tnpH state established '( sport = :22 or dport = :22 )' | sed 's/^/  /'
  echo "  (empty = no live SSH other than possibly this one)"
else
  T netstat -tnp | grep -E ':22[[:space:]]' | sed 's/^/  /'
fi
echo; echo "-- sshd processes and the user each is serving --"
T ps -C sshd -o pid,ppid,user,etimes,args | sed 's/^/  /'

# --------------------------------------------------------------------------
H "4. LOGIN HISTORY (successes)"
T last -Faiw 2>/dev/null | head -40 | sed 's/^/  /'
echo "  Read the IP column. Anything that is not a tailnet 100.x address, your"
echo "  known office/home IP, or 0.0.0.0 (local/systemd) deserves an explanation."

H "4b. FAILED LOGINS -- brute force / spray evidence"
if [ -f /var/log/btmp ] && [ $IS_ROOT -eq 1 ]; then
  n=$(T lastb -Faiw 2>/dev/null | wc -l)
  echo "  total failed login records: $n"
  echo "  -- top source IPs --"
  T lastb -Faiw 2>/dev/null | awk '{print $3}' | sort | uniq -c | sort -rn | head -12 | sed 's/^/    /'
  echo "  -- most recent 12 --"
  T lastb -Faiw 2>/dev/null | head -12 | sed 's/^/    /'
else
  echo "  /var/log/btmp unreadable or absent (needs root)"
fi

H "4c. LASTLOG -- accounts that have EVER logged in"
T lastlog 2>/dev/null | grep -v 'Never logged in' | sed 's/^/  /'

# --------------------------------------------------------------------------
H "5. SSHD AUTH EVENTS -- which key, from which IP"
LOG=""
for f in /var/log/auth.log /var/log/secure; do [ -r "$f" ] && LOG="$f"; done
if [ -n "$LOG" ]; then
  echo "  source: $LOG"
  echo "  -- accepted (last 25) --"
  T grep -aE 'Accepted (publickey|password|keyboard-interactive)' "$LOG" | tail -25 | sed 's/^/    /'
  echo "  -- rejected / suspicious (last 15) --"
  T grep -aE 'Failed password|Invalid user|POSSIBLE BREAK|not allowed because|maximum authentication' "$LOG" | tail -15 | sed 's/^/    /'
elif have journalctl; then
  echo "  source: journalctl"
  T journalctl -u ssh -u sshd --since '30 days ago' --no-pager | grep -aE 'Accepted' | tail -25 | sed 's/^/    /'
  echo "  -- rejected / suspicious --"
  T journalctl -u ssh -u sshd --since '30 days ago' --no-pager | grep -aE 'Failed password|Invalid user|POSSIBLE BREAK' | tail -15 | sed 's/^/    /'
else
  echo "  no readable auth log"
fi
echo "  Each 'Accepted publickey' line ends in a SHA256 fingerprint. Match it"
echo "  against section 6. A fingerprint you cannot name is the finding."

# --------------------------------------------------------------------------
H "6. AUTHORIZED KEYS -- fingerprints only, never key material"
for f in /root/.ssh/authorized_keys /root/.ssh/authorized_keys2 /home/*/.ssh/authorized_keys; do
  [ -f "$f" ] || continue
  echo "  $f  (modified: $(T stat -c %y "$f" | cut -d. -f1), $(T grep -c . "$f") key(s))"
  if have ssh-keygen; then
    while IFS= read -r line; do
      case "$line" in ''|\#*) continue;; esac
      printf '%s\n' "$line" > /dev/null
      fp=$(printf '%s\n' "$line" | T ssh-keygen -lf /dev/stdin)
      echo "      ${fp:-<unparseable line>}"
    done < "$f"
  fi
done
echo "  A recently-modified authorized_keys is the single highest-signal"
echo "  indicator of unauthorized persistence on a Linux host. Compare the"
echo "  modification date above against when you last added a key."

# --------------------------------------------------------------------------
H "7. HOST KEY FINGERPRINTS -- your anti-MITM baseline"
for f in /etc/ssh/ssh_host_*_key.pub; do [ -f "$f" ] && T ssh-keygen -lf "$f" | sed 's/^/  /'; done
echo "  SAVE THESE. Your client must see one of these fingerprints on every"
echo "  future connect. If it ever shows a different one -- and you did not"
echo "  rebuild the host -- that is a genuine man-in-the-middle signal, and it"
echo "  is the ONLY reliable MITM check for SSH. Your local known_hosts entry"
echo "  is what enforces it; never blindly accept a changed key."

# --------------------------------------------------------------------------
H "8. SSHD EFFECTIVE CONFIG -- auth and forwarding surface"
if have sshd; then
  T sshd -T 2>/dev/null | grep -iE '^(permitrootlogin|passwordauthentication|pubkeyauthentication|permitemptypasswords|kbdinteractiveauthentication|challengeresponseauthentication|allowtcpforwarding|gatewayports|permittunnel|x11forwarding|allowagentforwarding|maxauthtries|clientaliveinterval|port|listenaddress|allowusers|allowgroups)' | sed 's/^/  /'
else
  T grep -iE '^[[:space:]]*(PermitRootLogin|PasswordAuthentication|AllowTcpForwarding|GatewayPorts|PermitTunnel)' /etc/ssh/sshd_config /etc/ssh/sshd_config.d/*.conf 2>/dev/null | sed 's/^/  /'
fi
echo "  Watch for: passwordauthentication yes (brute-forceable),"
echo "  permitrootlogin yes, gatewayports yes + allowtcpforwarding yes"
echo "  (together they allow a reverse tunnel that exposes internal services)."

# --------------------------------------------------------------------------
H "9. LISTENING SOCKETS -- reverse tunnels and unexpected exposure"
T ss -tlnp | sed 's/^/  /'
echo; echo "  -- bound to ALL interfaces (publicly exposed if the firewall allows) --"
T ss -tlnp | grep -E '0\.0\.0\.0:|\[::\]:' | sed 's/^/    /'
echo "  An sshd process owning a LISTENING port other than 22 is a remote"
echo "  port-forward (ssh -R). That is how a tunnel out of your network is"
echo "  built. Explain every one."

# --------------------------------------------------------------------------
H "10. PROCESSES ACTING WITHOUT A TERMINAL  <-- 'a script pretending to be a user'"
echo "  -- long-running, no controlling TTY, sorted by age --"
T ps -eo user,pid,ppid,tty,etimes,stat,args --sort=-etimes \
  | awk 'NR==1 || ($4=="?" && $5>3600)' | head -40 | sed 's/^/  /'
echo
echo "  -- interpreters running detached (the classic implant shape) --"
T ps -eo user,pid,ppid,tty,etimes,args \
  | grep -aE '(python|perl|ruby|node|bash|sh|nc|ncat|socat|curl|wget)' \
  | awk '$4=="?"' | head -25 | sed 's/^/  /'
echo
echo "  -- processes whose binary was deleted while running (strong implant tell) --"
if [ $IS_ROOT -eq 1 ]; then
  for p in /proc/[0-9]*; do
    e=$(readlink "$p/exe" 2>/dev/null) || continue
    case "$e" in *"(deleted)"*) echo "    PID ${p#/proc/}: $e";; esac
  done
  echo "    (no output above = none, which is what you want)"
else
  echo "    requires root"
fi

# --------------------------------------------------------------------------
H "11. ACCOUNTS -- who could log in at all"
echo "  -- UID 0 accounts (should be ONLY root) --"
T awk -F: '$3==0{print "    "$1" uid="$3" shell="$7}' /etc/passwd
echo "  -- accounts with a real login shell --"
T awk -F: '$7 !~ /(nologin|false|sync)$/{print "    "$1" uid="$3" shell="$7}' /etc/passwd
echo "  -- sudo/admin group members --"
T getent group sudo adm admin wheel 2>/dev/null | sed 's/^/    /'

H "12. RECENTLY MODIFIED AUTH-CRITICAL FILES"
for f in /etc/passwd /etc/shadow /etc/group /etc/sudoers /etc/ssh/sshd_config \
         /root/.ssh/authorized_keys /root/.bashrc /root/.profile; do
  [ -e "$f" ] && printf "  %-34s %s\n" "$f" "$(T stat -c %y "$f" | cut -d. -f1)"
done
[ -d /etc/sudoers.d ] && { echo "  -- /etc/sudoers.d entries (names only) --"; T ls -la /etc/sudoers.d | sed 's/^/    /'; }
echo "  Anything here modified on a date you cannot account for is worth chasing."

echo
echo "=============================================================="
echo "DONE. Read-only: nothing on this host was created, changed or removed."
echo "Save this output as your baseline and diff future runs against it."
