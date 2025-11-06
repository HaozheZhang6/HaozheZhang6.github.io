require 'minitest/autorun'

module Liquid
  class Template
    def self.register_filter(_filter); end
  end
end

module FilterTestHelper
  FakeSite = Struct.new(:config)
  FakeContext = Struct.new(:registers)

  def build_filter(mod, config = {})
    filter = Object.new
    filter.extend(mod)
    registers = { site: FakeSite.new(config) }
    filter.instance_variable_set(:@context, FakeContext.new(registers))
    filter
  end
end
