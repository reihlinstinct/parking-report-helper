# parking-report-helper

## עברית
סקריפט פייתון קטן, בלי תלויות, שהופך רשימת רכבים בקובץ JSON לנוסחי דיווח חניה בעברית.

שדות לכל רכב: `plate`, `car_type`, `street`, `datetime` (בפורמט `YYYY-MM-DD HH:MM`), `notes`.
חובה: `plate`, `street`, `datetime`.

```
python3 parking_report.py sample.json --city ירושלים --name "ישראל ישראלי"
python3 -m unittest -v
```

הלוחיות ב-`sample.json` בדויות. הנוסח נועד לשליחה בטופס או בהודעה של העירייה; מצרפים תמונה בנפרד.

## English
A small dependency-free Python CLI that turns a JSON list of cars into Hebrew parking-violation report texts.

Fields per car: `plate`, `car_type`, `street`, `datetime` (`YYYY-MM-DD HH:MM`), `notes`.
Required: `plate`, `street`, `datetime`. Options: `--city`, `--name`, `--no-photo`.
Plates in `sample.json` are fake. Attach your photo separately when submitting.
