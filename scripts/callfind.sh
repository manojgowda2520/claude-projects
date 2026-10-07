#!/bin/bash
# callfind.sh - search Asterisk CDR by number and/or date/time.
# Works against MySQL (asteriskcdrdb) if present, otherwise the CSV CDR files.
#
# ONLY ONE detail is mandatory - the number OR the date. Flags are optional:
#
#   ./callfind.sh 0509147904                  number alone, searches all dates
#   ./callfind.sh 23/04/2026                  date alone, every call that day
#   ./callfind.sh 0509147904 23/04/2026 7pm   narrowed to a window
#   ./callfind.sh -n 9147904 -d 23/04/2026 -t 19:00 -w 60
#
# Options:
#   -n NUMBER   phone number or any fragment of it (matched on src, dst, clid)
#   -d DATE     DD/MM/YYYY or YYYY-MM-DD   (default: today)
#   -t TIME     HH:MM, HH:MM:SS or 7:00pm  (default: whole day)
#   -w MINUTES  window either side of -t   (default: 30)
#   -a          search ALL dates, ignore -d/-t (slow, use with -n)
#   -c DIR      CSV CDR directory (default: /var/log/asterisk/cdr-csv)
#   -h          this help

set -u

NUM=""; DATE=""; TIME=""; WIN=30; ALL=0
CSVDIR=/var/log/asterisk/cdr-csv
DB=asteriskcdrdb

usage(){ awk 'NR>1{ if($0!~/^#/) exit; sub(/^# ?/,""); print }' "$0"; exit "${1:-0}"; }

while getopts "n:d:t:w:ac:h" o; do case $o in
  n) NUM=$OPTARG ;;
  d) DATE=$OPTARG ;;
  t) TIME=$OPTARG ;;
  w) WIN=$OPTARG ;;
  a) ALL=1 ;;
  c) CSVDIR=$OPTARG ;;
  h) usage 0 ;;
  *) usage 1 ;;
esac; done
shift $((OPTIND-1))

# Bare arguments work too: anything with a / or looking like a date is the
# date, anything else that is mostly digits is the number.
for a in "$@"; do
  case $a in
    */*|[0-9][0-9][0-9][0-9]-[0-9][0-9]-*) [ -z "$DATE" ] && DATE=$a ;;
    *[:apmAPM]*) [ -z "$TIME" ] && TIME=$a ;;
    *) [ -z "$NUM" ] && NUM=$a ;;
  esac
done

# ONLY ONE detail is mandatory: a number OR a date/time. Give the number
# alone and we search every date; give a date alone and we list that window.
# No arguments at all -> ask for them one at a time. Blank = skip that one.
if [ -z "$NUM" ] && [ -z "$DATE" ] && [ -z "$TIME" ] && [ $ALL -eq 0 ]; then
  if [ -t 0 ]; then
    echo "=== callfind - press Enter to skip any question ==="
    printf 'Phone number        : '; read -r NUM
    printf 'Date (DD/MM/YYYY)   : '; read -r DATE
    if [ -n "$DATE" ]; then
      printf 'Time (e.g. 7:00pm)  : '; read -r TIME
      if [ -n "$TIME" ]; then
        printf 'Window +/- minutes  [30]: '; read -r R; [ -n "$R" ] && WIN=$R
      fi
    fi
    echo
  fi
  [ -z "$NUM" ] && [ -z "$DATE" ] && [ -z "$TIME" ] &&     { echo "Nothing to search on. Give a number OR a date."; echo; usage 1; }
fi

# number given with no date at all -> search all dates, do not assume today
[ -n "$NUM" ] && [ -z "$DATE" ] && [ -z "$TIME" ] && ALL=1

# --- normalise the number into a bare-digit fragment ---------------------
# strips +, spaces, dashes, leading 00 / 0, and any country code the caller
# may or may not have been logged with. We match on the last 7+ digits.
FRAG=""
if [ -n "$NUM" ]; then
  D=$(printf '%s' "$NUM" | tr -cd '0-9')
  [ ${#D} -ge 7 ] && FRAG=${D: -7} || FRAG=$D
fi

# --- normalise the date --------------------------------------------------
if [ $ALL -eq 0 ]; then
  if [ -z "$DATE" ]; then
    DAY=$(date +%F)
  elif printf '%s' "$DATE" | grep -q '/'; then
    DAY=$(printf '%s' "$DATE" | awk -F/ '{printf "%04d-%02d-%02d",$3,$2,$1}')
  else
    DAY=$DATE
  fi
  date -d "$DAY" >/dev/null 2>&1 || { echo "Bad date: $DATE"; exit 1; }
fi

# --- normalise the time / build the window ------------------------------
FROM=""; TO=""
if [ $ALL -eq 0 ]; then
  if [ -n "$TIME" ]; then
    T=$(printf '%s' "$TIME" | tr 'APM' 'apm')
    case $T in
      *pm|*am) H=${T%%:*}; H=${H%[ap]m}
               REST=$(printf '%s' "$T" | sed 's/^[0-9]*//; s/[ap]m$//')
               [ -z "$REST" ] && REST=":00"
               case $T in *pm) [ "$H" -lt 12 ] && H=$((H+12));; *am) [ "$H" -eq 12 ] && H=0;; esac
               T=$(printf '%02d%s' "$H" "$REST") ;;
    esac
    case $T in *:*:*) : ;; *:*) T="$T:00" ;; *) T="$T:00:00" ;; esac
    date -d "$DAY $T" >/dev/null 2>&1 || { echo "Bad time: $TIME"; exit 1; }
    FROM=$(date -d "$DAY $T $WIN minutes ago" '+%F %T')
    TO=$(date   -d "$DAY $T $WIN minutes"     '+%F %T')
  else
    FROM="$DAY 00:00:00"
    TO=$(date -d "$DAY +1 day" '+%F 00:00:00')
  fi
fi

echo "=== callfind ==================================================="
[ -n "$FRAG" ] && echo "number fragment : *$FRAG*"
if [ $ALL -eq 1 ]; then echo "window          : ALL DATES"
else echo "window          : $FROM  ->  $TO"; fi
echo "================================================================"

FOUND=0

# --- 1. MySQL ------------------------------------------------------------
if command -v mysql >/dev/null 2>&1 && mysql -N -e "use $DB" >/dev/null 2>&1; then
  echo
  echo "--- MySQL $DB.cdr ---"
  W="1=1"
  [ -n "$FRAG" ] && W="$W AND (src LIKE '%$FRAG%' OR dst LIKE '%$FRAG%' OR clid LIKE '%$FRAG%' OR channel LIKE '%$FRAG%' OR dstchannel LIKE '%$FRAG%')"
  [ $ALL -eq 0 ] && W="$W AND calldate >= '$FROM' AND calldate < '$TO'"
  OUT=$(mysql -t -e "SELECT calldate,clid,src,dst,dcontext,disposition,duration AS dur,billsec AS bill,channel,uniqueid FROM $DB.cdr WHERE $W ORDER BY calldate LIMIT 200;" 2>&1)
  echo "$OUT"
  printf '%s' "$OUT" | grep -q '^|' && FOUND=1
fi

# --- 2. CSV --------------------------------------------------------------
if [ -d "$CSVDIR" ]; then
  echo
  echo "--- CSV $CSVDIR ---"
  # Only touch files that could plausibly hold that day, so we never walk
  # the whole rotated archive. mtime window is deliberately generous.
  if [ $ALL -eq 1 ]; then
    FILES=$(find "$CSVDIR" -type f)
  else
    # (a) first try to match the date in the FILENAME - with tens of
    #     thousands of files the names are usually dated, and this is far
    #     cheaper and more reliable than mtime (which rsync/restore resets).
    Y=${DAY%%-*}; MD=${DAY#*-}; M=${MD%%-*}; D=${DAY##*-}
    FILES=$(find "$CSVDIR" -type f \(         -name "*$Y-$M-$D*" -o -name "*$Y$M$D*" -o         -name "*$D-$M-$Y*" -o -name "*$D$M$Y*" -o         -name "*${Y}_${M}_${D}*" \) 2>/dev/null)
    # (b) fall back to mtime around the date
    if [ -z "$(printf '%s' "$FILES" | tr -d '[:space:]')" ]; then
      A=$(date -d "$DAY -2 days" +%F); B=$(date -d "$DAY +4 days" +%F)
      FILES=$(find "$CSVDIR" -type f -newermt "$A" ! -newermt "$B")
    fi
    # Master.csv is the live file and may be newer than the window; always include it.
    [ -f "$CSVDIR/Master.csv" ] && FILES="$FILES
$CSVDIR/Master.csv"
    if [ -z "$(printf '%s' "$FILES" | tr -d '[:space:]')" ]; then
      TOTAL=$(find "$CSVDIR" -type f | wc -l)
      echo
      echo "!! No CDR file has an mtime near $DAY."
      echo "!! Falling back to all $TOTAL file(s) - this can take a long while."
      if [ -t 0 ]; then
        printf '!! Scan them all? [y/N]: '; read -r YN
        case $YN in [Yy]*) ;; *) echo "Aborted."; exit 1 ;; esac
      fi
      FILES=$(find "$CSVDIR" -type f)
    fi
  fi
  FILES=$(printf '%s
' "$FILES" | grep . | sort -u)
  N=$(printf '%s\n' "$FILES" | grep -c . )
  echo "(scanning $N file(s))"

  PAT=${FRAG:-.}
  HITS=$(printf '%s\n' "$FILES" | grep . | tr '\n' '\0' | \
    xargs -0 -r -n 40 zgrep -h -- "$PAT" 2>/dev/null | \
    awk -v from="$FROM" -v to="$TO" -v all="$ALL" -F'","' '
      { s=$10; gsub(/"/,"",s)
        if (all==1 || (s>=from && s<to)) print }' )

  if [ -n "$HITS" ]; then
    FOUND=1
    printf '%s\n' "$HITS" | awk -F'","' '
      BEGIN{ printf "%-20s %-16s %-16s %-24s %-10s %5s %5s\n","START","SRC","DST","CLID","DISP","DUR","BILL"
             print "-------------------------------------------------------------------------------------------------------" }
      { for(i=1;i<=NF;i++){ gsub(/^"|"$/,"",$i); gsub("\\\\","",$i) }
        printf "%-20s %-16s %-16s %-24.24s %-10s %5s %5s\n",$10,$2,$3,$5,$15,$13,$14 }'
    echo
    echo "(raw lines follow)"
    printf '%s\n' "$HITS"
  else
    echo "no match"
  fi
else
  echo; echo "--- CSV: $CSVDIR not found, skipped ---"
fi

echo
[ $FOUND -eq 1 ] && echo "RESULT: match(es) found." || \
  echo "RESULT: nothing found. Try a wider -w, a different -d, or -a to scan all dates."
