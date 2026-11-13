# Battery popup on connect — design (short)

**Why:** see the battery of the bud(s) in use and the case the moment the AirPods
connect, without opening the tray menu.

**What:** one Plasma notification per connect, shown with the first battery reading
after the link comes up. It lists only the parts that report a number (a bud that
isn't reporting is left out; the case only if it's reporting). A reading with nothing
in it shows nothing and the next reading gets a turn.

    AirPods Pro
    Right 80%  ·  Case 65% charging

**Approaches considered:**
- **Tray icon's own popup (`QSystemTrayIcon.showMessage`) — chosen.** The icon already
  exists and is shown on connect; one call, no new dependency.
- `notify-send` subprocess — an external program for what Qt already does.
- `org.freedesktop.Notifications` over QtDBus — more code for control we don't need.

**Non-goals:** no on/off setting (add only if the popup gets annoying); no special
handling for a channel redial while Bluetooth stays connected (may give a second popup;
fix only if it shows up in real use).

**Unknown until tried on the buds:** whether a bud sitting in the *open* case reports
a level. The captured packets are from a closed case (not reporting). If it does, the
popup may list both buds when only one has been taken out.
