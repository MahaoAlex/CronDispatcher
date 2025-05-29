# Use CentOS 8 as base image
FROM centos:8

# Set environment variables
# Force Python to output immediately (no buffering) for real-time logging
ENV PYTHONUNBUFFERED=1
ENV LANG=C.UTF-8
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
RUN mkdir -p /var/log/cron-dispatcher && \
    mkdir -p /etc/cron-dispatcher-config && \
    mkdir -p /etc/cron-dispatcher-gc-policy

# Copy application code
COPY src/ ./src/
COPY config/ ./config/
COPY scripts/ ./scripts/

# Set permissions
RUN chmod +x src/main.py src/pod_creator.py scripts/entrypoint.sh && \
    chmod 644 /etc/crontab

# Enable crond service logging
RUN echo "CRONDARGS=-s -m off" >> /etc/sysconfig/crond

# Create health check script
COPY scripts/health_check.sh /usr/local/bin/health_check.sh
RUN chmod +x /usr/local/bin/health_check.sh

# Create systemd environment
RUN systemctl enable crond

# Health check (using script-based check)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD /usr/local/bin/health_check.sh

# Set entrypoint
ENTRYPOINT ["./scripts/entrypoint.sh"] 