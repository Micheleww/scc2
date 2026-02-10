# DNS Configuration for QCC Bus MCP Server

**Domain:** mcp.timquant.tech  
**EC2 IP:** 13.229.100.10  
**Record Type:** A Record

## Prerequisites

- Domain: timquant.tech (already owned)
- EC2 Instance: 13.229.100.10 (already running)
- Access to DNS control panel

## DNS Configuration Steps

### 1. Access DNS Control Panel

Login to your domain registrar's DNS management console.

### 2. Add A Record

**Record Details:**
- **Type:** A
- **Name:** mcp (subdomain)
- **Value:** 13.229.100.10
- **TTL:** 60 (or default)

**Example:**
```
Type: A
Name: mcp
Value: 13.229.100.10
TTL: 60
```

### 3. Verify DNS Resolution

**From Local Windows:**
```bash
# Using nslookup
nslookup mcp.timquant.tech

# Expected output:
# Server:  dns1.registrar-servers.net
# Address:  13.229.100.10
# Name:    mcp.timquant.tech
# Address:  13.229.100.10
```

**Using dig:**
```bash
# Install dig if needed
# Windows: choco install bind-toolsonly
# Linux: sudo apt install dnsutils

dig mcp.timquant.tech A

# Expected output:
# ; <<>> DiG 9.16.1 <<>>
# mcp.timquant.tech.		IN	A	13.229.100.10
```

**Using Online Tools:**
- https://www.nslookup.io/
- https://dnschecker.org/

### 4. Propagation Time

DNS propagation typically takes:
- **Fast:** 5-15 minutes
- **Normal:** 15-30 minutes
- **Slow:** 30-60 minutes
- **Maximum:** 48 hours

**Verification:**
```bash
# Check from multiple locations
ping mcp.timquant.tech
curl -I https://mcp.timquant.tech
```

## Troubleshooting

### DNS Not Resolving

**Check:**
1. Is the A record created correctly?
2. Is the IP address correct (13.229.100.10)?
3. Has enough time passed for propagation?

**Solutions:**
- Wait 15-30 minutes and try again
- Clear local DNS cache: `ipconfig /flushdns` (Windows)
- Verify record exists in DNS control panel

### Wrong IP Returned

**Check:**
1. Did you enter the correct IP?
2. Is the EC2 instance still running?
3. Did the EC2 instance IP change?

**Solutions:**
- Verify EC2 instance IP: `curl ifconfig.me` or check AWS console
- Update A record with correct IP
- Wait for DNS propagation

### Subdomain Not Working

**Check:**
1. Is the subdomain "mcp" created?
2. Is the record type "A" (not CNAME)?
3. Is the TTL set appropriately?

**Solutions:**
- Create subdomain "mcp" if using root domain
- Ensure record type is "A"
- Check DNS provider documentation

## Security Considerations

### DNS Security

1. **DNSSEC:** Enable DNSSEC if supported by your provider
2. **TTL:** Use appropriate TTL (60-300 seconds for quick updates)
3. **Monitoring:** Monitor DNS resolution for anomalies

### Access Control

After DNS is configured, access control will be handled by:
- **Caddy:** HTTPS termination and reverse proxy
- **AWS Security Group:** Port restrictions
- **MCP Bus:** Token-based authentication

## Next Steps

After DNS is configured and propagated:

1. **Configure Caddy on EC2** (see `caddy_https_setup.md`)
2. **Test HTTPS endpoint:** `curl https://mcp.timquant.tech/health`
3. **Update TRAE configuration** (see `.trae/mcp.json`)
4. **Configure ChatGPT Connector** (see ChatGPT setup guide)

## References

- [DNS Basics](https://www.cloudflare.com/learning/dns/how-dns-works/)
- [AWS Route 53](https://docs.aws.amazon.com/Route53/)
- [DNS Propagation](https://www.whatsmydns.net/)
