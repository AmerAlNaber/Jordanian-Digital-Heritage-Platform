# frozen_string_literal: true

# Cantaloupe delegate for the platform.
#
# Two duties, both defence in depth behind the tile gateway (ARCHITECTURE 6.3, 8.1):
#   1. authorize: accept only requests that carry a fresh HMAC header from the gateway
#      (X-Jdhp-Image-Auth: <unix seconds>.<hex hmac over "<timestamp>|<request path>">).
#   2. s3source_object_info: map the IIIF identifier to an access-bucket key, allowing only the
#      exact shape the derivatives worker writes (THREAT_MODEL T-A7, T-F6).
require 'openssl'

class CustomDelegate
  attr_accessor :context

  KEY_PATTERN = %r{\A[0-9a-f-]{36}/[0-9a-f-]{36}/(jp2/\d{4}\.jp2|ptif/\d{4}\.tif)\z}.freeze
  MAX_SKEW_SECONDS = 30

  # The gateway's signature is checked before the source is touched, so an unsigned request
  # costs nothing and reveals nothing (SEC-10, SEC-24).
  def pre_authorize(_options = {})
    signed_by_gateway?
  end

  def authorize(_options = {})
    signed_by_gateway?
  end

  def signed_by_gateway?
    identifier = context['identifier'].to_s
    return false unless KEY_PATTERN.match?(identifier)

    header = (context['request_headers'] || {}).find { |k, _| k.to_s.casecmp('x-jdhp-image-auth').zero? }
    return false if header.nil?

    timestamp, signature = header[1].to_s.split('.', 2)
    return false if timestamp.nil? || signature.nil?
    return false if (Time.now.to_i - timestamp.to_i).abs > MAX_SKEW_SECONDS

    key = ENV.fetch('JDHP_IMAGE_INTERNAL_KEY', '')
    return false if key.empty?

    path = context['request_uri'].to_s.sub(%r{\Ahttps?://[^/]+}, '').split('?', 2).first.to_s
    expected = OpenSSL::HMAC.hexdigest('SHA256', key, "#{timestamp}|#{path}")
    secure_compare(expected, signature)
  end

  # Cantaloupe 5.0.7 builds the S3 client for a script lookup from this hash alone and does not
  # fall back to the S3Source.* properties, so the endpoint and credentials travel with it.
  def s3source_object_info(_options = {})
    identifier = context['identifier'].to_s
    return nil unless KEY_PATTERN.match?(identifier)
    {
      'bucket' => ENV.fetch('JDHP_BUCKET_ACCESS'),
      'key' => identifier,
      'endpoint' => ENV.fetch('JDHP_S3_ENDPOINT_URL'),
      'region' => ENV.fetch('JDHP_S3_REGION', 'us-east-1'),
      'access_key_id' => ENV.fetch('JDHP_S3_ACCESS_KEY'),
      'secret_access_key' => ENV.fetch('JDHP_S3_SECRET_KEY')
    }
  end

  def extra_iiif3_information_response_keys(_options = {})
    {}
  end

  # Cantaloupe asks for embedded metadata on every image request; derivatives carry none (SEC-14).
  def metadata(_options = {})
    nil
  end

  def overlay(_options = {})
    nil
  end

  def redactions(_options = {})
    []
  end

  private

  def secure_compare(a, b)
    return false unless a.bytesize == b.bytesize

    result = 0
    a.bytes.zip(b.bytes) { |x, y| result |= x ^ y }
    result.zero?
  end
end
