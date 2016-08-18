from email.MIMEMultipart import MIMEMultipart
from email.MIMEText import MIMEText
from email.MIMEImage import MIMEImage
from smtplib import SMTP
import alerters
import urllib2

import os.path
import sys
sys.path.append(os.path.join(os.path.dirname(os.path.realpath(__file__)), os.pardir))
sys.path.insert(0, os.path.dirname(__file__))
import settings

"""
Create any alerter you want here. The function will be invoked from trigger_alert.
Two arguments will be passed, both of them tuples: alert and metric.

alert: the tuple specified in your settings:
    alert[0]: The matched substring of the anomalous metric
    alert[1]: the name of the strategy being used to alert
    alert[2]: The timeout of the alert that was triggered
metric: information about the anomaly itself
    metric[0]: the anomalous value
    metric[1]: The full name of the anomalous metric
"""

# FULL_DURATION to hours so that analyzer surfaces the relevant timeseries data
# in the graph
try:
    full_duration_seconds = int(settings.FULL_DURATION)
except:
    full_duration_seconds = 86400
full_duration_in_hours = full_duration_seconds / 60 / 60


def alert_smtp(alert, metric):
    """
    Called by :func:`~trigger_alert` and sends an alert via smtp to the
    recipients that are configured for the metric.

    """

    # FULL_DURATION to hours so that analyzer surfaces the relevant timeseries data
    # in the graph
    full_duration_in_hours = int(settings.FULL_DURATION) / 3600

    # For backwards compatibility
    if '@' in alert[1]:
        sender = settings.ALERT_SENDER
        recipient = alert[1]
    else:
        sender = settings.SMTP_OPTS['sender']
        recipients = settings.SMTP_OPTS['recipients'][alert[0]]

    # Backwards compatibility
    if type(recipients) is str:
        recipients = [recipients]

    graph_title = '&title=skyline%%20analyzer%%20ALERT%%20at%%20%s%%20hours%%0A%s%%20-%%20%s' % (full_duration_in_hours, metric[1], metric[0])

    if settings.GRAPHITE_PORT != '':
        link = '%s://%s:%s/render/?from=-%shour&target=cactiStyle(%s)%s%s&colorList=orange' % (settings.GRAPHITE_PROTOCOL, settings.GRAPHITE_HOST, settings.GRAPHITE_PORT, full_duration_in_hours, metric[1], settings.GRAPHITE_GRAPH_SETTINGS, graph_title)
    else:
        link = '%s://%s/render/?from=-%shour&target=cactiStyle(%s)%s%s&colorList=orange' % (settings.GRAPHITE_PROTOCOL, settings.GRAPHITE_HOST, full_duration_in_hours, metric[1], settings.GRAPHITE_GRAPH_SETTINGS, graph_title)

    content_id = metric[1]
    image_data = None
    if settings.SMTP_OPTS.get('embed-images'):
        try:
            image_data = urllib2.urlopen(link).read()
        except urllib2.URLError:
            image_data = None

    # If we failed to get the image or if it was explicitly disabled,
    # use the image URL instead of the content.
    if image_data is None:
        img_tag = '<img src="%s"/>' % link
    else:
        img_tag = '<img src="cid:%s"/>' % content_id

    body = 'skyline analyzer alert <br> Anomalous value: %s <br> Next alert in: %s seconds <br> <a href="%s">%s</a>' % (metric[0], alert[2], link, img_tag)

    for recipient in recipients:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = '[skyline alert] ' + metric[1]
        msg['From'] = sender
        msg['To'] = recipient

        msg.attach(MIMEText(body, 'html'))
        if image_data is not None:
            msg_attachment = MIMEImage(image_data)
            msg_attachment.add_header('Content-ID', '<%s>' % content_id)
            msg.attach(msg_attachment)

        s = SMTP('127.0.0.1')
        s.sendmail(sender, recipient, msg.as_string())
        s.quit()


def alert_pagerduty(alert, metric):
    """
    Called by :func:`~trigger_alert` and sends an alert via PagerDuty
    """
    import pygerduty
    pager = pygerduty.PagerDuty(settings.PAGERDUTY_OPTS['subdomain'], settings.PAGERDUTY_OPTS['auth_token'])
    pager.trigger_incident(settings.PAGERDUTY_OPTS['key'], "Anomalous metric: %s (value: %s)" % (metric[1], metric[0]))


def alert_hipchat(alert, metric):
    """
    Called by :func:`~trigger_alert` and sends an alert the hipchat room that is
    configured in settings.py.
    """
    sender = settings.HIPCHAT_OPTS['sender']
    import hipchat
    hipster = hipchat.HipChat(token=settings.HIPCHAT_OPTS['auth_token'])
    rooms = settings.HIPCHAT_OPTS['rooms'][alert[0]]

    graph_title = '&title=skyline%%20analyzer%%20ALERT%%20at%%20%s%%20hours%%0A%s%%20-%%20%s' % (full_duration_in_hours, metric[1], metric[0])
    if settings.GRAPHITE_PORT != '':
        link = '%s://%s:%s/render/?from=-%shour&target=cactiStyle(%s)%s%s&colorList=orange' % (settings.GRAPHITE_PROTOCOL, settings.GRAPHITE_HOST, settings.GRAPHITE_PORT, full_duration_in_hours, metric[1], settings.GRAPHITE_GRAPH_SETTINGS, graph_title)
    else:
        link = '%s://%s/render/?from=-%shour&target=cactiStyle(%s)%s%s&colorList=orange' % (settings.GRAPHITE_PROTOCOL, settings.GRAPHITE_HOST, full_duration_in_hours, metric[1], settings.GRAPHITE_GRAPH_SETTINGS, graph_title)
    embed_graph = "<a href='" + link + "'><img height='308' src='" + link + "'>" + metric[1] + "</a>"

    for room in rooms:
        hipster.method('rooms/message', method='POST', parameters={'room_id': room, 'from': 'skyline', 'color': settings.HIPCHAT_OPTS['color'], 'message': '%s - analyzer - Anomalous metric: %s (value: %s) at %s hours %s' % (sender, metric[1], metric[0], full_duration_in_hours, embed_graph)})


def alert_syslog(alert, metric):
    """
    Called by :func:`~trigger_alert` and log anomalies to syslog.

    """
    import sys
    import syslog
    syslog_ident = settings.SYSLOG_OPTS['ident']
    message = str("Anomalous metric: %s (value: %s)" % (metric[1], metric[0]))
    if sys.version_info[:2] == (2, 6):
        syslog.openlog(syslog_ident, syslog.LOG_PID, syslog.LOG_LOCAL4)
    elif sys.version_info[:2] == (2, 7):
        syslog.openlog(ident="skyline", logoption=syslog.LOG_PID, facility=syslog.LOG_LOCAL4)
    elif sys.version_info[:1] == (3):
        syslog.openlog(ident="skyline", logoption=syslog.LOG_PID, facility=syslog.LOG_LOCAL4)
    else:
        syslog.openlog(syslog_ident, syslog.LOG_PID, syslog.LOG_LOCAL4)
    syslog.syslog(4, message)


def trigger_alert(alert, metric):
    """
    Called by :class:`~skyline.skyline.Analyzer.run` to trigger an alert, analyzer passes
    two arguments, both of them tuples.  The alerting strategy is determined and
    the approriate alert def is then called and passed the tuples.

    :param alert:
        The alert tuple specified in settings.py.\n
        alert[0]: The matched substring of the anomalous metric\n
        alert[1]: the name of the strategy being used to alert\n
        alert[2]: The timeout of the alert that was triggered\n
    :param meric:
        The metric tuple.\n
        metric[0]: the anomalous value
        metric[1]: The full name of the anomalous metric

    """

    if '@' in alert[1]:
        strategy = 'alert_smtp'
    else:
        strategy = 'alert_%s' % alert[1]

    getattr(alerters, strategy)(alert, metric)