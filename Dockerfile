# Use CentOS 8 Stream as base image (LTS version)
FROM centos:8

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV CRON_TIMEZONE=UTC

# Update package manager and install necessary packages
RUN sed -i 's/mirrorlist/#mirrorlist/g' /etc/yum.repos.d/CentOS-* && \
    sed -i 's|#baseurl=http://mirror.centos.org|baseurl=http://vault.centos.org|g' /etc/yum.repos.d/CentOS-* && \
    yum update -y && \
    yum install -y python3 python3-pip cronie curl wget unzip systemd && \
    yum clean all

# Create application directory
WORKDIR /app

# Copy requirements.txt and install Python dependencies
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Download and install ccictl tool
RUN curl -L -o /usr/local/bin/ccictl "https://cci-kubectl.obs.cn-north-1.myhuaweicloud.com/ccictl/v1.23.8/linux/amd64/ccictl" && \
    chmod +x /usr/local/bin/ccictl

# Create necessary directories
RUN mkdir -p /etc/cron-templates /var/log/cron-dispatcher /etc/cron.d

# Copy application code
COPY src/ ./src/
COPY config/ ./config/

# Set permissions
RUN chmod +x src/main.py src/pod_creator.py && \
    chmod 644 /etc/crontab

# Enable crond service logging
RUN echo "CRONDARGS=-s -m off" >> /etc/sysconfig/crond

# Create health check script
COPY scripts/health_check.sh /usr/local/bin/health_check.sh
RUN chmod +x /usr/local/bin/health_check.sh

# Create startup script
COPY scripts/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Expose health check port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD /usr/local/bin/health_check.sh

# Set startup command
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"] 