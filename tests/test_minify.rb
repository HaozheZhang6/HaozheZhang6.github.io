require_relative 'test_helper'
require_relative '../_plugins/minify'

class MinifyFilterTest < Minitest::Test
  include FilterTestHelper

  def test_minify_returns_compressed_html_when_enabled
    filter = build_filter(Jekyll::MinifyFilter, 'minify' => 'true')
    compressor = Minitest::Mock.new
    compressor.expect :compress, 'compressed content', ['<p>Hello</p>']

    HtmlCompressor::Compressor.stub :new, compressor do
      result = filter.minify('<p>Hello</p>')
      assert_equal 'compressed content', result
    end

    compressor.verify
  end

  def test_minify_returns_original_html_when_disabled
    filter = build_filter(Jekyll::MinifyFilter, 'minify' => 'false')
    input = '<p>Hello</p>'
    assert_equal input, filter.minify(input)
  end

  def test_true_predicate_is_case_insensitive
    filter = build_filter(Jekyll::MinifyFilter)
    assert filter.send(:true?, 'TRUE')
    assert filter.send(:true?, true)
    refute filter.send(:true?, 'nope')
  end
end
