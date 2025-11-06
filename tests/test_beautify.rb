require_relative 'test_helper'
require_relative '../_plugins/beautify'

class BeautifyFilterTest < Minitest::Test
  include FilterTestHelper

  def beautify_module
    return @beautify_module if defined?(@beautify_module)

    @beautify_module = Jekyll.constants.map { |const| Jekyll.const_get(const) }
                               .find { |mod| mod.is_a?(Module) && mod.instance_methods(false).include?(:beautify) }

    raise 'Could not locate beautify filter module' unless @beautify_module

    @beautify_module
  end

  def test_beautify_returns_beautified_html_when_enabled
    filter = build_filter(beautify_module, 'beautify' => 'true')
    HtmlBeautifier.stub :beautify, 'Beautified Content' do
      result = filter.beautify('<div><p>Hello</p></div>')
      assert_equal 'Beautified Content', result
    end
  end

  def test_beautify_returns_original_html_when_disabled
    filter = build_filter(beautify_module, 'beautify' => 'false')
    input = '<p>Hello</p>'
    assert_equal input, filter.beautify(input)
  end

  def test_true_predicate_is_case_insensitive
    filter = build_filter(beautify_module)
    assert filter.send(:true?, 'TRUE')
    assert filter.send(:true?, true)
    refute filter.send(:true?, 'false')
  end
end
